from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
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
        owner_path = Path(first["roba"]["owner_file"])
        first_owner = json.loads(owner_path.read_text(encoding="utf-8"))

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
        assert session.require("status")(session="review")["running"] is True
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
