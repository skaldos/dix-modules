from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path
from roba import daemon_status, start_daemon, stop_daemon

ROOT = Path(__file__).parents[1]


def _select(references: object, object_id: str) -> dict[str, object]:
    assert isinstance(references, list)
    matches = [item for item in references if item.get("object_id") == object_id]
    assert len(matches) == 1
    return matches[0]


def _environment(runtime_root: Path, logs_root: Path) -> dict[str, str]:
    return {"ROBA_RUNTIME_ROOT": str(runtime_root), "ROBA_LOGS_ROOT": str(logs_root)}


def test_real_catalog_loom_and_isolated_tmux_lifecycles(monkeypatch) -> None:
    root = Path(tempfile.mkdtemp(prefix="dxc-e2e-", dir="/tmp"))
    runtime_root = root / "rt"
    logs_root = root / "logs"
    cockpit_root = Path("/tmp") / f"dxc-w-{uuid.uuid4().hex[:8]}"
    catalog_path = root / "daemons.toml"
    catalog_path.write_text(
        f'''[daemons.running]
daemon_id = "running"
runtime_root = "{runtime_root}"
logs_root = "{logs_root}"

[daemons.stopped]
daemon_id = "stopped"
runtime_root = "{runtime_root}"
logs_root = "{logs_root}"

[daemons.broken]
daemon_id = "broken"
runtime_root = "{runtime_root}"
logs_root = "{logs_root}"
'''
    )
    environment = _environment(runtime_root, logs_root)
    running = start_daemon("running", env=environment)
    start_daemon("broken", env=environment)
    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", str(cockpit_root))
    monkeypatch.setenv(
        "DIX_COCKPIT_TMUX_CONFIG", str(ROOT / "cockpit/integrations/tmux/cockpit.conf")
    )

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    created: list[tuple[str, str]] = []
    try:
        for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
        loaded.append("skaldos/visidata")
        modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
        loaded.append("skaldos/cockpit")

        def create(instance_id: str, use: str):
            value = compositions.create_instance(
                CompositionInstanceSpec(instance_id, use, {}, root),
                owner_scope_id="cockpit-e2e",
            )
            created.append(("cockpit-e2e", instance_id))
            return value.api

        catalog = create("catalog", "skaldos/cockpit/daemon_catalog")
        connections = create("connections", "skaldos/cockpit/roba_connections")
        control = create("control", "dix/roba/control")
        loom = create("loom", "dix/roba/loom")
        session = create("session", "skaldos/cockpit/cockpit_session")

        config = {
            "daemon_id": "running",
            "runtime_root": str(runtime_root),
            "logs_root": str(logs_root),
            "timeout": 5.0,
        }
        control.require("set")(config)
        control.require("bootstrap")(
            control_locator=str(running.control_locator),
            control_token=running.control_token,
        )

        entries = catalog.require("load")(catalog_path)
        rows = connections.require("resolve_all")(entries)
        assert [row["state"] for row in rows] == ["running", "stopped", "error"]
        assert rows[0]["connection"]["control_token"] == running.control_token
        assert set(rows[1]["connection"]) == {
            "daemon_id",
            "runtime_root",
            "logs_root",
            "timeout",
        }
        assert rows[2]["connection"] is None and rows[2]["error"]
        assert daemon_status(daemon="id:running", env=environment)["daemon_id"] == "running"
        assert daemon_status(daemon="id:broken", env=environment)["daemon_id"] == "broken"
        assert not (runtime_root / "daemons/stopped").exists()

        first = session.require("start")(
            session="dix",
            catalog=str(catalog_path),
            logo="dix",
            count=3,
            control_command=["sleep", "300"],
            header_command=["sleep", "300"],
            attach=False,
        )
        second = session.require("start")(
            session="review",
            catalog=str(catalog_path),
            logo="roba",
            count=3,
            control_command=["sleep", "300"],
            header_command=["sleep", "300"],
            attach=False,
        )
        assert first["socket"] == second["socket"]
        opened = session.require("open_connection")(
            session="dix",
            catalog_id="running",
            command=["sleep", "300"],
        )
        again = session.require("open_connection")(
            session="dix",
            catalog_id="running",
            command=["sleep", "300"],
        )
        assert opened["action"] == "created" and again["action"] == "focused"
        assert session.require("stop")(session="dix") is True
        assert session.require("status")(session="review")["running"] is True
        assert session.require("stop")(session="review") is True

        stopped_seed = rows[1]["connection"]
        connection = _select(loom.require("execute")(stopped_seed), "connection")
        daemon = _select(
            loom.require("execute")(connection["value"], connection["object_id"]), "daemon"
        )
        connect = _select(
            loom.require("execute")(daemon["value"], daemon["object_id"]), "connect"
        )
        start = _select(
            loom.require("execute")(connect["value"], connect["object_id"]), "start"
        )
        capability = _select(
            loom.require("execute")(start["value"], start["object_id"]), "connection"
        )
        assert capability["value"]["daemon_id"] == "stopped"
        assert daemon_status(daemon="id:stopped", env=environment)["daemon_id"] == "stopped"
        daemon = _select(
            loom.require("execute")(capability["value"], "connection"), "daemon"
        )
        connect = _select(loom.require("execute")(daemon["value"], "daemon"), "connect")
        stop = _select(loom.require("execute")(connect["value"], "connect"), "stop")
        _select(loom.require("execute")(stop["value"], "stop"), "connection")
        assert not (runtime_root / "daemons/stopped").exists()
    finally:
        for owner, instance_id in reversed(created):
            compositions.destroy_instance(owner, instance_id)
        for daemon_id in ("stopped", "broken", "running"):
            if (runtime_root / "daemons" / daemon_id / "daemon.sock").exists():
                stop_daemon(daemon=f"id:{daemon_id}", env=environment)
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(cockpit_root, ignore_errors=True)
    assert not cockpit_root.exists()
