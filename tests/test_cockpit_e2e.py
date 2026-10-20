from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


def _select(references: object, object_id: str) -> dict[str, object]:
    assert isinstance(references, list)
    selected = [
        item
        for item in references
        if isinstance(item, dict) and item.get("object_id") == object_id
    ]
    assert len(selected) == 1
    return selected[0]


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_real_privileged_runtime_reuse_reset_and_two_sessions(monkeypatch) -> None:
    root = Path(tempfile.gettempdir()) / f"dxe-{uuid.uuid4().hex[:8]}"
    runtime_root = root / "run"
    state_root = root / "state"
    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", str(runtime_root))
    monkeypatch.setenv("DIX_COCKPIT_STATE_ROOT", str(state_root))
    monkeypatch.setenv(
        "DIX_COCKPIT_TMUX_CONFIG", str(ROOT / "cockpit/integrations/tmux/cockpit.conf")
    )

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    instance = None
    owner_shell = None
    try:
        for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
        loaded.append("skaldos/visidata")
        modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
        loaded.append("skaldos/cockpit")
        instance = compositions.create_instance(
            CompositionInstanceSpec(
                "session", "skaldos/cockpit/cockpit_session", {}, ROOT / "cockpit"
            ),
            owner_scope_id="cockpit-real-e2e",
        )
        session = instance.api

        owner_shell = applications.create_instance(
            ApplicationInstanceSpec(
                "owner-shell", "skaldos/cockpit/owner_shell", {}, ROOT / "cockpit"
            ),
            owner_scope_id="cockpit-real-e2e",
        )

        def start(name: str, logo: str = "dix") -> dict[str, object]:
            return session.require("start")(
                session=name,
                logo=logo,
                shell_command=["sleep", "300"],
                status_command=["sleep", "300"],
                attach=False,
            )

        first = start("dix")
        assert first["running"] is True
        assert first["created"] == {"roba": True, "tmux": True}
        assert first["tmux"]["server_owned"] is True
        assert first["tmux"]["session_owned"] is True
        owner_path = Path(first["roba"]["owner_file"])
        first_owner = json.loads(owner_path.read_text(encoding="utf-8"))

        server_marker = subprocess.run(
            [
                "tmux",
                "-S",
                first["tmux"]["socket"],
                "show-options",
                "-gqv",
                "@cockpit-server-owner",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        session_marker = subprocess.run(
            [
                "tmux",
                "-S",
                first["tmux"]["socket"],
                "show-options",
                "-v",
                "-t",
                "dix",
                "@cockpit-owner",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert server_marker.stdout.strip() == "skaldos.dix-cockpit.tmux-server.v1"
        assert session_marker.stdout.strip() == "skaldos.dix-cockpit.tmux-session.v1"

        reused = start("dix")
        assert reused["created"] == {"roba": False, "tmux": False}
        assert reused["roba"]["pid"] == first["roba"]["pid"]

        # A missing tmux session is rebuilt around the still-owned daemon.
        paths = instance.runtime.paths(session="dix")
        assert instance.runtime.tmux.require("stop")(session="dix", socket=paths["socket"])
        rebuilt = start("dix")
        assert rebuilt["created"] == {"roba": False, "tmux": True}
        for tmux_arguments in (
            ["show-environment", "-t", "dix"],
            ["show-options", "-t", "dix"],
            ["list-panes", "-t", "dix", "-F", "#{pane_title}"],
        ):
            metadata = subprocess.run(
                ["tmux", "-S", paths["socket"], *tmux_arguments],
                capture_output=True,
                text=True,
                check=False,
            )
            assert metadata.returncode == 0, metadata.stderr
            assert "TOKEN" not in metadata.stdout.upper()
            assert first_owner["control_token"] not in metadata.stdout

        # The real owner environment drives both public ROBA command surfaces.
        owner_environment = owner_shell.runtime._environment("dix")
        launcher = root / "dix-roba-cli.py"
        build = subprocess.run(
            [
                str(DIX / ".venv/bin/python"),
                "-m",
                "dix.bootstrap",
                "build",
                str(DIX / "examples/launchers/dix_roba.toml"),
                "--output",
                str(launcher),
                "--replace",
            ],
            cwd=DIX,
            capture_output=True,
            text=True,
            check=False,
        )
        assert build.returncode == 0, build.stderr
        dix_status = subprocess.run(
            [str(DIX / ".venv/bin/python"), str(launcher), "daemon", "status"],
            env={**owner_environment, "PYTHONUNBUFFERED": "1"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert dix_status.returncode == 0, dix_status.stderr
        assert "control_token" not in (dix_status.stdout + dix_status.stderr).lower()
        contexts = subprocess.run(
            [str(DIX / ".venv/bin/roba-ctl"), "ctx", "list"],
            env=owner_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert contexts.returncode == 0, contexts.stderr
        assert json.loads(contexts.stdout) == {"contexts": []}

        # The isolated interactive Zsh reads only Cockpit startup state and exposes completion.
        host_home = root / "host-home"
        host_home.mkdir()
        (host_home / ".zshrc").write_text("export HOST_ZSHRC_LOADED=1\n")
        owner_environment["HOME"] = str(host_home)
        shell = subprocess.run(
            [
                "zsh",
                "-d",
                "-i",
                "-c",
                'print -r -- "$ZDOTDIR|$HISTFILE|${+functions[_dix_cockpit]}|${HOST_ZSHRC_LOADED-}"',
            ],
            env=owner_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert shell.returncode == 0, shell.stderr
        assert shell.stdout.strip().endswith("|1|")
        assert str(state_root / "sessions/dix/zsh") in shell.stdout

        review = start("review", "roba")
        assert review["running"] is True
        assert first["tmux"]["socket"] == review["tmux"]["socket"]
        assert review["tmux"]["server_owned"] is True
        assert review["tmux"]["session_owned"] is True
        assert Path(review["roba"]["owner_file"]) != owner_path

        reset = session.require("reset")(
            session="dix",
            logo="dix",
            shell_command=["sleep", "300"],
            status_command=["sleep", "300"],
            attach=False,
        )
        reset_owner = json.loads(Path(reset["roba"]["owner_file"]).read_text(encoding="utf-8"))
        assert reset["running"] is True
        assert reset_owner["control_token"] != first_owner["control_token"]
        assert session.require("status")(session="review")["running"] is True

        stopped = session.require("stop")(session="dix")
        assert stopped["roba_stopped"] is True and stopped["tmux_stopped"] is True
        review_status = session.require("status")(session="review")
        assert review_status["running"] is True
        assert review_status["tmux"]["server_owned"] is True
        assert session.require("stop")(session="review")["stopped"] is True
        assert not (runtime_root / "tmux.sock").exists()
        assert (state_root / "sessions/dix/logs").is_dir()
        assert (state_root / "sessions/review/logs").is_dir()
    finally:
        if owner_shell is not None:
            applications.destroy_instance("cockpit-real-e2e", "owner-shell")
        if instance is not None:
            for name in ("dix", "review"):
                try:
                    status = instance.api.require("status")(session=name)
                    if status.get("state") not in {"foreign", "drift"}:
                        instance.api.require("stop")(session=name)
                except RuntimeError:
                    pass
            compositions.destroy_instance("cockpit-real-e2e", "session")
        socket = runtime_root / "tmux.sock"
        subprocess.run(
            ["tmux", "-S", str(socket), "kill-server"],
            capture_output=True,
            check=False,
        )
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_real_master_workspace_traverses_private_roba_store_and_data(monkeypatch) -> None:
    root = Path(tempfile.gettempdir()) / f"dxu-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", str(root / "run"))
    monkeypatch.setenv("DIX_COCKPIT_STATE_ROOT", str(root / "state"))
    monkeypatch.setenv(
        "DIX_COCKPIT_TMUX_CONFIG", str(ROOT / "cockpit/integrations/tmux/cockpit.conf")
    )

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    session_instance = None
    master = None
    try:
        for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
        loaded.append("skaldos/visidata")
        modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
        loaded.append("skaldos/cockpit")
        session_instance = compositions.create_instance(
            CompositionInstanceSpec(
                "master-session", "skaldos/cockpit/cockpit_session", {}, ROOT / "cockpit"
            ),
            owner_scope_id="cockpit-master-real-e2e",
        )
        started = session_instance.api.require("start_master")(
            session="master",
            shell_command=["sleep", "300"],
            status_command=["sleep", "300"],
            workbench_command=["sleep", "300"],
            attach=False,
        )
        assert started["running"] is True
        assert started["workbench"]["action"] == "created"
        panes = subprocess.run(
            [
                "tmux",
                "-S",
                str(started["tmux"]["socket"]),
                "list-panes",
                "-t",
                "master:control",
                "-F",
                "#{@cockpit-pane-role}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert panes.returncode == 0, panes.stderr
        assert set(panes.stdout.splitlines()) == {
            "skaldos.dix-cockpit.runtime-status.v1",
            "skaldos.dix-cockpit.owner-shell.v1",
            "skaldos.dix-cockpit.master-workbench.v1",
        }

        master = applications.create_instance(
            ApplicationInstanceSpec(
                "master-workbench",
                "skaldos/cockpit/master_workbench",
                {},
                ROOT / "cockpit",
            ),
            owner_scope_id="cockpit-master-real-e2e",
        )
        observed: list[object] = []

        def traverse(execute, seed, logo, confirm):
            observed.append(seed)
            assert logo == "dix" and confirm is True
            connection = _select(execute(seed), "connection")["value"]
            store = _select(execute(connection, "connection"), "store")
            connect = _select(execute(store["value"], "store"), "connect")
            create_context = _select(execute(connect["value"], "connect"), "create")
            context = _select(
                execute(
                    {
                        **create_context["value"],
                        "context_id": "workspace",
                        "name": "Workspace",
                    },
                    "create",
                ),
                "connection",
            )["value"]
            context_store = _select(execute(context, "connection"), "store")
            context_connect = _select(execute(context_store["value"], "store"), "connect")
            create_instance = _select(
                execute(context_connect["value"], "connect"), "create"
            )
            instance = _select(
                execute(
                    {
                        **create_instance["value"],
                        "instance_id": "draft",
                        "name": "Draft",
                        "state": {},
                    },
                    "create",
                ),
                "connection",
            )["value"]
            data = _select(execute(instance, "connection"), "data")
            data_connect = _select(execute(data["value"], "data"), "connect")
            offers = execute(data_connect["value"], "connect")
            write = _select(offers, "write")
            written = _select(
                execute(
                    {**write["value"], "key": "message", "value": {"ok": True}},
                    "write",
                ),
                "value",
            )
            assert written["value"] == {"ok": True}
            listed = _select(execute(_select(offers, "list")["value"], "list"), "keys")
            assert listed["value"] == ["message"]
            return 0

        master.runtime.workbench = FakeApi(start=traverse)
        argv = ["--session", "master", "--logo", "dix"]
        assert master.api.require("main")(argv) == 0
        assert len(observed) == 1
        seed = observed[0]
        assert isinstance(seed, dict) and seed["control_token"]
        assert str(seed["control_token"]) not in " ".join(argv)
        assert session_instance.api.require("stop")(session="master")["stopped"] is True
    finally:
        if master is not None:
            applications.destroy_instance("cockpit-master-real-e2e", "master-workbench")
        if session_instance is not None:
            try:
                status = session_instance.api.require("status")(session="master")
                if status.get("state") not in {"foreign", "drift"}:
                    session_instance.api.require("stop")(session="master")
            except RuntimeError:
                pass
            compositions.destroy_instance("cockpit-master-real-e2e", "master-session")
        subprocess.run(
            ["tmux", "-S", str(root / "run/tmux.sock"), "kill-server"],
            capture_output=True,
            check=False,
        )
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        shutil.rmtree(root, ignore_errors=True)
