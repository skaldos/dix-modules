from __future__ import annotations

import importlib
import shutil
import subprocess
import tempfile
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
            return _completed(args)
        if operation == "set-option":
            session = args[args.index("-t") + 1].removeprefix("=")
            option = args[-2]
            self.options[(session, option)] = args[-1]
            return _completed(args)
        if operation == "show-options":
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
        if operation == "kill-session":
            session = args[args.index("-t") + 1].removeprefix("=")
            del self.sessions[session]
            self.options = {key: value for key, value in self.options.items() if key[0] != session}
            return _completed(args)
        if operation == "list-sessions":
            if not self.sessions:
                return _completed(args, 1, stderr="no sessions")
            return _completed(args, stdout="\n".join(self.sessions) + "\n")
        return _completed(args)


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
