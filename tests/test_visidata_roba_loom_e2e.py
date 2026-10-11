from __future__ import annotations

import copy
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path


def _pick(session, object_id: str):
    matches = [
        (index, reference)
        for index, reference in enumerate(session.references)
        if reference.object_id == object_id
    ]
    assert len(matches) == 1, (object_id, session.references)
    return session.inspect(matches[0][0])


def _follow(session, object_id: str, changes: dict[str, object] | None = None):
    draft = _pick(session, object_id)
    if changes:
        assert isinstance(draft.value, dict)
        draft.value.update(copy.deepcopy(changes))
    session.execute_draft(draft)
    return draft


def _cleanup(config: dict[str, object]) -> None:
    from roba import resolve_daemon_locator, stop_daemon

    environment = {
        **{key: value for key, value in os.environ.items() if not key.startswith("ROBA_")},
        "ROBA_RUNTIME_ROOT": str(config["runtime_root"]),
        "ROBA_LOGS_ROOT": str(config["logs_root"]),
    }
    endpoint = resolve_daemon_locator(f"id:{config['daemon_id']}", env=environment).socket
    if endpoint.is_socket():
        stop_daemon(
            daemon=f"id:{config['daemon_id']}",
            timeout=float(config["timeout"]),
            env=environment,
        )
    shutil.rmtree(Path(str(config["runtime_root"])), ignore_errors=True)
    shutil.rmtree(Path(str(config["logs_root"])), ignore_errors=True)


def test_real_isolated_roba_lifecycle_uses_only_the_generic_session(tmp_path: Path) -> None:
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    instances: list[str] = []
    short_root = Path(tempfile.mkdtemp(prefix="u58-", dir="/tmp"))
    config = {
        "daemon_id": "u58",
        "runtime_root": str(short_root / "r"),
        "logs_root": str(short_root / "l"),
        "timeout": 5.0,
    }
    runtime_prefixes: list[str] = []
    try:
        for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(Path(__file__).parents[1] / "visidata", module_id="skaldos/visidata")
        loaded.append("skaldos/visidata")
        loom = compositions.create_instance(
            CompositionInstanceSpec("loom", "dix/roba/loom", {}, tmp_path),
            owner_scope_id="visidata-real-e2e",
        )
        instances.append("loom")
        workbench = compositions.create_instance(
            CompositionInstanceSpec(
                "workbench", "skaldos/visidata/loom_workbench", {}, tmp_path
            ),
            owner_scope_id="visidata-real-e2e",
        )
        instances.append("workbench")
        runtime_prefixes = [
            loom.runtime.__class__.__module__,
            workbench.runtime.__class__.__module__,
        ]

        # From here on the test client knows only Session/ObjectReferences and never calls Loom.
        session = workbench.api.require("create_session")(loom.api.require("execute"), config)
        assert [item.object_id for item in session.references] == ["connection"]
        _follow(session, "connection")
        _follow(session, "daemon")
        _follow(session, "connect")
        _follow(session, "start")
        capability = _pick(session, "connection")
        assert Path(capability.value["daemon_socket"]).is_socket()

        # Re-enter through the retained complete capability reference and inspect status.
        session.execute_draft(capability)
        _follow(session, "daemon")
        _follow(session, "connect")
        assert [item.object_id for item in session.references] == ["status", "stop"]
        _follow(session, "status")
        assert _pick(session, "daemon_status").value["daemon_id"] == config["daemon_id"]
        _follow(session, "daemon_status")
        assert session.references == ()

        # Context Store create through the same retained capability.
        session.execute_draft(capability)
        _follow(session, "store")
        _follow(session, "connect")
        create = _pick(session, "create")
        create.value.update({"context_id": "workbench", "name": "Workbench"})
        session.execute_draft(create)
        direct = _pick(session, "connection")
        assert direct.value["context_id"] == "workbench"

        # A repeated create is a real provider error and keeps the local draft/reference set.
        before = copy.deepcopy(session.references)
        with pytest.raises(Exception, match="409"):
            session.execute_draft(create)
        assert session.references == before
        assert create.value["context_id"] == "workbench"

        # Context data write/read are selected and filled only through returned drafts.
        session.execute_draft(direct)
        _follow(session, "data")
        _follow(session, "connect")
        _follow(
            session,
            "write",
            {"key": "profile", "value": {"nested": [1, {"ok": True}]}},
        )
        assert _pick(session, "value").value == {"nested": [1, {"ok": True}]}

        session.execute_draft(direct)
        _follow(session, "data")
        _follow(session, "connect")
        _follow(session, "read", {"key": "profile"})
        assert _pick(session, "value").value == {"nested": [1, {"ok": True}]}

        # Stop via the same capability and prove the runtime disappeared.
        session.execute_draft(capability)
        _follow(session, "daemon")
        _follow(session, "connect")
        _follow(session, "stop")
        assert [item.object_id for item in session.references] == ["connection"]
        assert not (Path(str(config["runtime_root"])) / "daemons" / str(config["daemon_id"])).exists()
    finally:
        _cleanup(config)
        for instance_id in reversed(instances):
            compositions.destroy_instance("visidata-real-e2e", instance_id)
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        for prefix in runtime_prefixes:
            assert prefix not in sys.modules
            assert not any(name.startswith(f"{prefix}.") for name in sys.modules)
        assert not Path(str(config["runtime_root"])).exists()
        assert not Path(str(config["logs_root"])).exists()
        shutil.rmtree(short_root, ignore_errors=True)
