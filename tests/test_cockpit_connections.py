from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path
from roba import daemon_status, start_daemon, stop_daemon

ROOT = Path(__file__).parents[1]


@pytest.fixture
def graph(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    connection = compositions.create_instance(
        CompositionInstanceSpec(
            "connections", "skaldos/cockpit/roba_connections", {}, tmp_path
        ),
        owner_scope_id="cockpit-connection-test",
    )
    control = compositions.create_instance(
        CompositionInstanceSpec("control", "dix/roba/control", {}, tmp_path),
        owner_scope_id="cockpit-connection-test",
    )
    try:
        yield connection.api, control.api
    finally:
        compositions.destroy_instance("cockpit-connection-test", "control")
        compositions.destroy_instance("cockpit-connection-test", "connections")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def _entry(root: Path, daemon_id: str = "cockpit") -> dict[str, object]:
    return {
        "catalog_id": "local",
        "daemon_id": daemon_id,
        "runtime_root": str(root / "runtime"),
        "logs_root": str(root / "logs"),
        "timeout": 5.0,
    }


def _environment(entry: dict[str, object]) -> dict[str, str]:
    return {
        "ROBA_RUNTIME_ROOT": str(entry["runtime_root"]),
        "ROBA_LOGS_ROOT": str(entry["logs_root"]),
    }


def test_stopped_entry_materializes_basic_connection_without_side_effect(graph) -> None:
    connection, _control = graph
    root = Path(tempfile.mkdtemp(prefix="dxc-", dir="/tmp"))
    shutil.rmtree(root)
    entry = _entry(root)
    result = connection.require("resolve")(entry)
    assert result["state"] == "stopped"
    assert result["connection"] == {
        key: entry[key] for key in ("daemon_id", "runtime_root", "logs_root", "timeout")
    }
    assert result["error"] is None
    assert not root.exists()


def test_running_entry_uses_control_credentials_and_materializes_capability(graph) -> None:
    connection, control = graph
    root = Path(tempfile.mkdtemp(prefix="dxc-", dir="/tmp"))
    entry = _entry(root, "running")
    environment = _environment(entry)
    creation = start_daemon("running", timeout=5, env=environment)
    try:
        control.require("set")({key: value for key, value in entry.items() if key != "catalog_id"})
        control.require("bootstrap")(
            control_locator=str(creation.control_locator),
            control_token=creation.control_token,
        )
        result = connection.require("resolve")(entry)
        assert result["state"] == "running", result["error"]
        assert result["error"] is None
        capability = result["connection"]
        assert isinstance(capability, dict)
        assert set(capability) == {
            "daemon_id",
            "runtime_root",
            "logs_root",
            "timeout",
            "pid",
            "daemon_socket",
            "control_socket",
            "control_token",
        }
        assert capability["control_token"] == creation.control_token
        assert daemon_status(daemon="id:running", env=environment)["daemon_id"] == "running"
    finally:
        stop_daemon(daemon="id:running", timeout=5, env=environment)
        shutil.rmtree(root, ignore_errors=True)


def test_running_without_valid_dix_control_is_visible_error_and_not_fallback(graph) -> None:
    connection, _control = graph
    root = Path(tempfile.mkdtemp(prefix="dxc-", dir="/tmp"))
    entry = _entry(root, "unmanaged")
    environment = _environment(entry)
    start_daemon("unmanaged", timeout=5, env=environment)
    try:
        result = connection.require("resolve")(entry)
        assert result["state"] == "error"
        assert result["connection"] is None
        assert result["daemon_status"] is None
        assert isinstance(result["error"], str) and result["error"]
        assert daemon_status(daemon="id:unmanaged", env=environment)["daemon_id"] == "unmanaged"
    finally:
        stop_daemon(daemon="id:unmanaged", timeout=5, env=environment)
        shutil.rmtree(root, ignore_errors=True)


def test_invalid_entry_fails_before_any_provider_access(graph) -> None:
    connection, _control = graph
    with pytest.raises(TypeError, match="exactly"):
        connection.require("resolve")({"daemon_id": "missing"})
