from __future__ import annotations

import json
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
    loaded: list[str] = []
    instance = None
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
