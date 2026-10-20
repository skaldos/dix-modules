from __future__ import annotations

import importlib
import shutil
import socket as socket_module
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]
TMUX_CONFIG = ROOT / "cockpit/integrations/tmux/cockpit.conf"


@pytest.fixture
def workspace(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "tmux",
            "skaldos/cockpit/tmux_workspace",
            {"tmux_config": str(TMUX_CONFIG)},
            tmp_path,
        ),
        owner_scope_id="cockpit-tmux-test",
    )
    runtime_module = importlib.import_module(instance.runtime.__class__.__module__)
    try:
        yield instance.api, runtime_module
    finally:
        compositions.destroy_instance("cockpit-tmux-test", "tmux")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


class FakeTmux:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []
        self.sessions: dict[str, list[str]] = {}
        self.options: dict[tuple[str, str], str] = {}
        self.global_options: dict[str, str] = {}
        self.panes: dict[str, list[str]] = {}
        self.pane_options: dict[tuple[str, str], str] = {}
        self.pane_dead: dict[str, bool] = {}
        self.selected_pane: str | None = None
        self._next_pane = 1

    def __call__(self, command, **kwargs):
        args = list(command)
        self.calls.append((args, dict(kwargs["env"])))
        operation = next(
            (
                item
                for item in (
                    "has-session",
                    "list-windows",
                    "new-session",
                    "select-window",
                    "attach-session",
                    "new-window",
                    "kill-session",
                    "list-sessions",
                    "kill-server",
                    "set-option",
                    "show-options",
                    "list-panes",
                    "split-window",
                    "select-pane",
                    "respawn-pane",
                    "kill-pane",
                )
                if item in args
            ),
            "",
        )
        if operation == "has-session":
            session = args[args.index("-t") + 1].removeprefix("=")
            return _completed(args, 0 if session in self.sessions else 1)
        if operation == "new-session":
            session = args[args.index("-s") + 1]
            self.sessions[session] = ["control"]
            pane = self._new_pane()
            self.panes[session] = [pane]
            return _completed(args)
        if operation == "set-option":
            if "-g" in args:
                self.global_options[args[-2]] = args[-1]
                return _completed(args)
            if "-p" in args:
                pane = self._pane(args[args.index("-t") + 1])
                self.pane_options[(pane, args[-2])] = args[-1]
                return _completed(args)
            session = args[args.index("-t") + 1].removeprefix("=")
            option = args[-2]
            self.options[(session, option)] = args[-1]
            return _completed(args)
        if operation == "show-options":
            if "-gqv" in args:
                value = self.global_options.get(args[-1], "")
                return _completed(args, stdout=value + "\n")
            session = args[args.index("-t") + 1].removeprefix("=")
            value = self.options.get((session, args[-1]))
            return _completed(args, 0 if value is not None else 1, stdout=(value or "") + "\n")
        if operation == "list-windows":
            session = args[args.index("-t") + 1].removeprefix("=")
            return _completed(args, stdout="\n".join(self.sessions[session]) + "\n")
        if operation == "new-window":
            session = args[args.index("-t") + 1].removeprefix("=")
            self.sessions[session].append(args[args.index("-n") + 1])
            return _completed(args)
        if operation == "list-panes":
            session = args[args.index("-t") + 1].removeprefix("=").split(":", 1)[0]
            lines = [
                "\t".join(
                    (
                        pane,
                        self.pane_options.get((pane, "@cockpit-pane-role"), ""),
                        "1" if self.pane_dead.get(pane, False) else "0",
                    )
                )
                for pane in self.panes[session]
            ]
            return _completed(args, stdout="\n".join(lines) + "\n")
        if operation == "split-window":
            target = self._pane(args[args.index("-t") + 1])
            session = self._pane_session(target)
            pane = self._new_pane()
            index = self.panes[session].index(target)
            self.panes[session].insert(index if "-b" in args else index + 1, pane)
            return _completed(args, stdout=f"{pane}\n" if "-P" in args else "")
        if operation == "select-pane":
            self.selected_pane = self._pane(args[args.index("-t") + 1])
            return _completed(args)
        if operation == "respawn-pane":
            pane = self._pane(args[args.index("-t") + 1])
            self.pane_dead[pane] = False
            return _completed(args)
        if operation == "kill-pane":
            pane = self._pane(args[args.index("-t") + 1])
            session = self._pane_session(pane)
            self.panes[session].remove(pane)
            self._remove_pane(pane)
            return _completed(args)
        if operation == "kill-session":
            session = args[args.index("-t") + 1].removeprefix("=")
            del self.sessions[session]
            for pane in self.panes.pop(session, []):
                self._remove_pane(pane)
            self.options = {key: value for key, value in self.options.items() if key[0] != session}
            if not self.sessions:
                self.global_options.clear()
            return _completed(args)
        if operation == "list-sessions":
            if not self.sessions:
                return _completed(args, 1, stderr="no server running")
            return _completed(args, stdout="\n".join(self.sessions) + "\n")
        if operation == "kill-server":
            self.sessions.clear()
            self.options.clear()
            self.global_options.clear()
            self.panes.clear()
            self.pane_options.clear()
            self.pane_dead.clear()
            return _completed(args)
        return _completed(args)

    def mark_dead(self, pane: str) -> None:
        self.pane_dead[self._pane(pane)] = True

    def _new_pane(self) -> str:
        pane = f"%{self._next_pane}"
        self._next_pane += 1
        self.pane_dead[pane] = False
        return pane

    def _pane(self, target: str) -> str:
        if target.startswith("%"):
            if not any(target in panes for panes in self.panes.values()):
                raise AssertionError(f"unknown pane target: {target}")
            return target
        plain = target.removeprefix("=")
        session_window, dot, raw_index = plain.rpartition(".")
        if not dot:
            raise AssertionError(f"invalid pane target: {target}")
        session = session_window.split(":", 1)[0]
        return self.panes[session][int(raw_index) - 1]

    def _pane_session(self, pane: str) -> str:
        return next(session for session, panes in self.panes.items() if pane in panes)

    def _remove_pane(self, pane: str) -> None:
        self.pane_dead.pop(pane, None)
        self.pane_options = {
            key: value for key, value in self.pane_options.items() if key[0] != pane
        }


def _completed(
    args: list[str], returncode: int = 0, *, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_fake_plans_use_one_socket_and_only_server_start_uses_config(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    monkeypatch.setenv("TMUX", "/tmp/host,1,0")
    socket = api.require("socket_path")(tmp_path / "short")
    environment = {
        "DIX_COCKPIT_SESSION": "dix",
        "DIX_COCKPIT_TMUX_SOCKET": str(socket),
    }
    first = api.require("start")(
        session="dix",
        socket=socket,
        control_command=["control-window", "--catalog", "/tmp/catalog.toml"],
        environment=environment,
        attach=False,
    )
    second = api.require("start")(
        session="dix",
        socket=socket,
        control_command=["control-window"],
        environment=environment,
        attach=False,
    )
    assert first["created"] is True and second["created"] is False
    assert first["server_owned"] is True and first["session_owned"] is True
    assert fake.global_options == {
        "@cockpit-server-owner": "skaldos.dix-cockpit.tmux-server.v1"
    }
    commands = [call for call, _env in fake.calls]
    assert all(command[:3] == ["tmux", "-S", str(socket)] for command in commands)
    configured = [command for command in commands if "-f" in command]
    assert len(configured) == 1 and "new-session" in configured[0]
    assert all("TMUX" not in env for _command, env in fake.calls)
    assert "'/tmp/catalog.toml'" not in configured[0][-1]

    opened = api.require("open_window")(
        session="dix",
        socket=socket,
        catalog_id="my unsafe/id",
        command=["connection-window", "--catalog-id", "my unsafe/id"],
    )
    focused = api.require("open_window")(
        session="dix",
        socket=socket,
        catalog_id="my unsafe/id",
        command=["connection-window"],
    )
    assert opened["action"] == "created" and focused["action"] == "focused"
    assert opened["window"] == focused["window"]
    assert "/" not in opened["window"] and " " not in opened["window"]
    assert api.require("stop")(session="dix", socket=socket) is True
    assert fake.sessions == {}


def test_fake_rejects_foreign_server_and_foreign_session_without_mutation(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    socket = api.require("socket_path")(tmp_path / "foreign")
    fake.sessions["foreign"] = ["control"]
    before_sessions = dict(fake.sessions)
    before_options = dict(fake.options)

    status = api.require("status")(session="dix", socket=socket)
    assert status["server_running"] is True
    assert status["server_owned"] is False
    with pytest.raises(RuntimeError, match="server without Cockpit ownership"):
        api.require("start")(
            session="dix",
            socket=socket,
            control_command=["shell"],
            environment={},
            attach=False,
        )
    with pytest.raises(RuntimeError, match="unowned tmux server"):
        api.require("stop")(session="dix", socket=socket)
    assert fake.sessions == before_sessions
    assert fake.options == before_options

    fake.global_options["@cockpit-server-owner"] = "skaldos.dix-cockpit.tmux-server.v1"
    fake.sessions["dix"] = ["control"]
    with pytest.raises(RuntimeError, match="session without Cockpit ownership"):
        api.require("start")(
            session="dix",
            socket=socket,
            control_command=["shell"],
            environment={},
            attach=False,
        )
    assert ("dix", "@cockpit-owner") not in fake.options


def test_fake_reuses_owned_server_and_stops_only_the_last_session(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    socket = api.require("socket_path")(tmp_path / "shared")
    for session in ("dix", "review"):
        result = api.require("start")(
            session=session,
            socket=socket,
            control_command=["shell"],
            environment={},
            attach=False,
        )
        assert result["owned"] is True
    assert len([args for args, _env in fake.calls if "-f" in args]) == 1
    assert api.require("stop")(session="dix", socket=socket) is True
    assert list(fake.sessions) == ["review"]
    assert fake.global_options
    assert api.require("stop")(session="review", socket=socket) is True
    assert fake.sessions == {}
    assert fake.global_options == {}


def test_fake_recovers_only_a_proven_dead_stale_socket(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    socket = api.require("socket_path")(tmp_path / "stale")
    socket.parent.mkdir(parents=True)
    stale = socket_module.socket(socket_module.AF_UNIX)
    stale.bind(str(socket))
    stale.close()

    result = api.require("start")(
        session="dix",
        socket=socket,
        control_command=["shell"],
        environment={},
        attach=False,
    )
    assert result["owned"] is True
    assert len([args for args, _env in fake.calls if "-f" in args]) == 1


def test_runtime_layout_and_tmux_process_environment_are_secret_free(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    monkeypatch.setenv("ROBA_CONTROL_TOKEN", "must-not-reach-tmux")
    socket = api.require("socket_path")(tmp_path / "runtime")
    api.require("start")(
        session="dix",
        socket=socket,
        control_command=["dix-cockpit-shell", "--session", "dix"],
        environment={
            "DIX_COCKPIT_SESSION": "dix",
            "DIX_COCKPIT_SHELL": "dix-cockpit-shell",
        },
        attach=False,
    )
    api.require("layout_runtime")(
        session="dix",
        socket=socket,
        status_command=["dix-cockpit-runtime-status", "--session", "dix"],
    )
    api.require("update_runtime_status")(
        session="dix", socket=socket, logo="dix", daemon_state="running"
    )
    assert all("ROBA_CONTROL_TOKEN" not in environment for _call, environment in fake.calls)
    joined = "\n".join(" ".join(call) for call, _environment in fake.calls)
    assert "must-not-reach-tmux" not in joined
    assert "ROBA_CONTROL_TOKEN" not in joined
    assert "DIX Cockpit Runtime" in joined
    assert "Owner Shell" in joined

    with pytest.raises(ValueError, match="secret key"):
        api.require("start")(
            session="other",
            socket=socket,
            control_command=["shell"],
            environment={"ROBA_CONTROL_TOKEN": "forbidden"},
            attach=False,
        )


def test_master_workbench_pane_is_role_driven_focused_and_respawned(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    socket = api.require("socket_path")(tmp_path / "master")
    api.require("start")(
        session="dix",
        socket=socket,
        control_command=["owner-shell"],
        environment={},
        attach=False,
    )
    api.require("layout_runtime")(
        session="dix", socket=socket, status_command=["runtime-status"]
    )

    created = api.require("open_master_workbench")(
        session="dix",
        socket=socket,
        command=["master-workbench", "--session", "dix"],
    )
    focused = api.require("open_master_workbench")(
        session="dix", socket=socket, command=["must-not-run"]
    )
    assert created["action"] == "created"
    assert focused == {**created, "action": "focused"}
    assert fake.pane_options[(created["pane_id"], "remain-on-exit")] == "on"
    assert (
        fake.pane_options[(created["pane_id"], "@cockpit-pane-role")]
        == "skaldos.dix-cockpit.master-workbench.v1"
    )
    assert len(fake.panes["dix"]) == 3

    fake.mark_dead(created["pane_id"])
    respawned = api.require("open_master_workbench")(
        session="dix", socket=socket, command=["master-workbench", "--session", "dix"]
    )
    assert respawned == {**created, "action": "respawned"}
    assert fake.pane_dead[created["pane_id"]] is False
    assert len(fake.panes["dix"]) == 3
    joined = "\n".join(" ".join(call) for call, _environment in fake.calls)
    assert "respawn-pane" in joined
    assert "ROBA_CONTROL_TOKEN" not in joined


def test_master_workbench_rejects_ambiguous_or_missing_roles(
    workspace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, runtime_module = workspace
    fake = FakeTmux()
    monkeypatch.setattr(runtime_module.subprocess, "run", fake)
    socket = api.require("socket_path")(tmp_path / "roles")
    api.require("start")(
        session="dix", socket=socket, control_command=["shell"], environment={}, attach=False
    )
    with pytest.raises(RuntimeError, match="owner shell pane role"):
        api.require("open_master_workbench")(
            session="dix", socket=socket, command=["workbench"]
        )

    api.require("layout_runtime")(
        session="dix", socket=socket, status_command=["status"]
    )
    first = api.require("open_master_workbench")(
        session="dix", socket=socket, command=["workbench"]
    )
    duplicate = fake._new_pane()
    fake.panes["dix"].append(duplicate)
    fake.pane_options[(duplicate, "@cockpit-pane-role")] = (
        "skaldos.dix-cockpit.master-workbench.v1"
    )
    with pytest.raises(RuntimeError, match="ambiguous"):
        api.require("open_master_workbench")(
            session="dix", socket=socket, command=["workbench"]
        )
    assert first["pane_id"] in fake.panes["dix"]


def test_socket_limit_is_checked_before_tmux(workspace, tmp_path: Path) -> None:
    api, _runtime_module = workspace
    with pytest.raises(RuntimeError, match="exceeds platform limit"):
        api.require("socket_path")(tmp_path / ("x" * 180))


def test_tmux_config_contains_the_complete_isolated_control_surface() -> None:
    config = TMUX_CONFIG.read_text()
    for fragment in (
        "set -g mouse off",
        "setw -g mode-keys vi",
        "set -g prefix C-a",
        "set -g prefix2 C-b",
        "set -sg escape-time 1",
        "base-index 1",
        "pane-base-index 1",
        "bind r source-file",
        "bind | split-window -h",
        "bind - split-window -v",
        '"$DIX_COCKPIT_SHELL" --session "#{session_name}"',
        "bind h select-pane -L",
        "bind C-h previous-window",
        "bind H resize-pane -L 5",
        "bind Escape copy-mode",
        "copy-pipe-and-cancel",
        "bind p run-shell",
        "bind C-p paste-buffer",
        "copy-mode-vi v",
        "bind Up if-shell",
        "bind Down if-shell",
        "focus-events on",
        "alacritty:RGB",
        'default-terminal "screen-256color"',
        "pane-border-status top",
        "history-limit 50000",
    ):
        assert fragment in config
    assert "source ~/.tmux" not in config
    assert "tpm" not in config.lower()


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_real_tmux_smoke_uses_only_the_isolated_socket(workspace) -> None:
    api, _runtime_module = workspace
    root = Path(tempfile.gettempdir()) / f"dxc-{uuid.uuid4().hex[:8]}"
    socket = api.require("socket_path")(root)
    try:
        result = api.require("start")(
            session="smoke",
            socket=socket,
            control_command=["sleep", "300"],
            environment={
                "DIX_COCKPIT_SESSION": "smoke",
                "DIX_COCKPIT_TMUX_SOCKET": str(socket),
                "DIX_COCKPIT_TMUX_CONFIG": str(TMUX_CONFIG),
                "DIX_COCKPIT_CLIPBOARD_COPY": "/bin/cat",
                "DIX_COCKPIT_CLIPBOARD_PASTE": "/bin/cat",
            },
            attach=False,
        )
        assert result["created"] is True
        server_owner = subprocess.run(
            ["tmux", "-S", str(socket), "show-options", "-gqv", "@cockpit-server-owner"],
            capture_output=True,
            text=True,
            check=False,
        )
        session_owner = subprocess.run(
            ["tmux", "-S", str(socket), "show-options", "-v", "-t", "smoke", "@cockpit-owner"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert server_owner.stdout.strip() == "skaldos.dix-cockpit.tmux-server.v1"
        assert session_owner.stdout.strip() == "skaldos.dix-cockpit.tmux-session.v1"
        opened = api.require("open_window")(
            session="smoke",
            socket=socket,
            catalog_id="real",
            command=["sleep", "300"],
        )
        assert opened["action"] == "created"
        status = api.require("status")(session="smoke", socket=socket)
        assert status["running"] is True
        assert status["windows"] == ["control", opened["window"]]
    finally:
        try:
            api.require("stop")(session="smoke", socket=socket)
        finally:
            subprocess.run(
                ["tmux", "-S", str(socket), "kill-server"],
                capture_output=True,
                check=False,
            )
            shutil.rmtree(root, ignore_errors=True)
    assert not socket.exists()


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_real_tmux_master_pane_remains_visible_and_respawns_in_place(workspace) -> None:
    api, _runtime_module = workspace
    root = Path(tempfile.gettempdir()) / f"dxm-{uuid.uuid4().hex[:8]}"
    socket = api.require("socket_path")(root)
    try:
        api.require("start")(
            session="master",
            socket=socket,
            control_command=["sleep", "300"],
            environment={},
            attach=False,
        )
        api.require("layout_runtime")(
            session="master", socket=socket, status_command=["sleep", "300"]
        )
        created = api.require("open_master_workbench")(
            session="master",
            socket=socket,
            command=["sh", "-c", "exit 7"],
        )
        assert created["action"] == "created"

        dead = ""
        for _attempt in range(100):
            probe = subprocess.run(
                [
                    "tmux",
                    "-S",
                    str(socket),
                    "display-message",
                    "-p",
                    "-t",
                    created["pane_id"],
                    "#{pane_dead}",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            dead = probe.stdout.strip()
            if dead == "1":
                break
            time.sleep(0.01)
        assert dead == "1"
        respawned = api.require("open_master_workbench")(
            session="master", socket=socket, command=["sleep", "300"]
        )
        assert respawned == {**created, "action": "respawned"}
        assert (
            subprocess.run(
                [
                    "tmux",
                    "-S",
                    str(socket),
                    "display-message",
                    "-p",
                    "-t",
                    created["pane_id"],
                    "#{pane_dead}",
                ],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            == "0"
        )
    finally:
        try:
            api.require("stop")(session="master", socket=socket)
        finally:
            subprocess.run(
                ["tmux", "-S", str(socket), "kill-server"],
                capture_output=True,
                check=False,
            )
            shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_real_foreign_server_without_target_session_is_never_mutated(workspace) -> None:
    api, _runtime_module = workspace
    root = Path(tempfile.gettempdir()) / f"dxf-{uuid.uuid4().hex[:8]}"
    socket = api.require("socket_path")(root)
    root.mkdir(parents=True)
    created = subprocess.run(
        [
            "tmux",
            "-S",
            str(socket),
            "-f",
            "/dev/null",
            "new-session",
            "-d",
            "-s",
            "foreign",
            "sleep 300",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    try:
        before = subprocess.run(
            ["tmux", "-S", str(socket), "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert before.stdout.splitlines() == ["foreign"]
        status = api.require("status")(session="dix", socket=socket)
        assert status["server_running"] is True and status["server_owned"] is False
        with pytest.raises(RuntimeError, match="server without Cockpit ownership"):
            api.require("start")(
                session="dix",
                socket=socket,
                control_command=["sleep", "300"],
                environment={},
                attach=False,
            )
        with pytest.raises(RuntimeError, match="unowned tmux server"):
            api.require("stop")(session="dix", socket=socket)
        after = subprocess.run(
            ["tmux", "-S", str(socket), "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert after.returncode == 0
        assert after.stdout == before.stdout
        owner = subprocess.run(
            ["tmux", "-S", str(socket), "show-options", "-gqv", "@cockpit-server-owner"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert owner.stdout == ""
    finally:
        subprocess.run(
            ["tmux", "-S", str(socket), "kill-server"],
            capture_output=True,
            check=False,
        )
        shutil.rmtree(root, ignore_errors=True)
