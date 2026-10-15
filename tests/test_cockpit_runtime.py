from __future__ import annotations

import json
import stat
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path
from roba import start_daemon, stop_daemon

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


@pytest.fixture
def cockpit_runtime(monkeypatch: pytest.MonkeyPatch):
    suffix = uuid.uuid4().hex[:8]
    root = Path("/tmp") / f"dx212-{suffix}"
    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", str(root / "run"))
    monkeypatch.setenv("DIX_COCKPIT_STATE_ROOT", str(root / "state"))

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
        CompositionInstanceSpec("runtime", "skaldos/cockpit/roba_runtime", {}, ROOT / "cockpit"),
        owner_scope_id="cockpit-runtime-test",
    )
    try:
        yield instance.api, root, instance.runtime
    finally:
        status = instance.api.require("status")(session="dix")
        if status.get("owned") is True:
            instance.api.require("stop")(session="dix")
        compositions.destroy_instance("cockpit-runtime-test", "runtime")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        if root.exists():
            import shutil

            shutil.rmtree(root)


def test_runtime_owns_reuses_and_stops_one_private_daemon(cockpit_runtime) -> None:
    runtime, root, _runtime_object = cockpit_runtime

    assert runtime.require("status")(session="dix")["state"] == "stopped"
    first = runtime.require("start")(session="dix")
    assert first["state"] == "running"
    assert first["owned"] is True
    assert first["created"] is True
    assert "token" not in json.dumps(first).lower()

    owner_path = Path(first["owner_file"])
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    assert stat.S_IMODE(owner_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((root / "run").stat().st_mode) == 0o700
    assert stat.S_IMODE((root / "state").stat().st_mode) == 0o700

    second = runtime.require("start")(session="dix")
    assert second["created"] is False
    assert second["pid"] == first["pid"]
    assert (
        json.loads(owner_path.read_text(encoding="utf-8"))["control_token"]
        == owner["control_token"]
    )

    environment = runtime.require("owner_environment")(session="dix")
    assert environment["ROBA_DAEMON"] == "id:default"
    assert environment["ROBA_CONTROL"] == "id:default"
    assert environment["ROBA_CONTROL_TOKEN"] == owner["control_token"]
    assert environment["DIX_COCKPIT_SESSION"] == "dix"

    stopped = runtime.require("stop")(session="dix")
    assert stopped["stopped"] is True
    assert not (root / "run/sessions/dix").exists()
    assert (root / "state/sessions/dix/logs").is_dir()


def test_runtime_rejects_tampered_capability_without_stopping_daemon(
    cockpit_runtime,
) -> None:
    runtime, _, _runtime_object = cockpit_runtime
    started = runtime.require("start")(session="dix")
    owner_path = Path(started["owner_file"])
    owner = json.loads(owner_path.read_text(encoding="utf-8"))
    tampered = dict(owner)
    tampered["control_token"] = "not-the-control-capability"
    owner_path.write_text(json.dumps(tampered), encoding="utf-8")
    owner_path.chmod(0o600)

    status = runtime.require("status")(session="dix")
    assert status["state"] == "drift"
    assert status["running"] is True
    with pytest.raises(RuntimeError, match="capability"):
        runtime.require("stop")(session="dix")

    owner_path.write_text(json.dumps(owner), encoding="utf-8")
    owner_path.chmod(0o600)
    assert runtime.require("stop")(session="dix")["stopped"] is True


def test_runtime_replaces_only_stale_artifacts(cockpit_runtime) -> None:
    runtime, root, _runtime_object = cockpit_runtime
    owner_path = root / "run/sessions/dix/owner.json"
    owner_path.parent.mkdir(parents=True)
    owner_path.write_text("stale", encoding="utf-8")

    started = runtime.require("start")(session="dix")
    assert started["created"] is True
    assert json.loads(owner_path.read_text(encoding="utf-8"))["owner"].startswith(
        "skaldos.dix-cockpit"
    )


def test_session_paths_reject_invalid_names_and_oversized_socket_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cockpit.compositions.config.runtime import Runtime

    runtime = Runtime(context=None, config={})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must match"):
        runtime.session_paths("../escape")

    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", "/tmp/" + "x" * 100)
    with pytest.raises(ValueError, match="platform limit"):
        runtime.session_paths("dix")


def test_owner_artifact_never_uses_ambient_roba_roots(
    cockpit_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, root, _runtime_object = cockpit_runtime
    monkeypatch.setenv("ROBA_RUNTIME_ROOT", "/tmp/ambient-roba")
    monkeypatch.setenv("ROBA_LOGS_ROOT", "/tmp/ambient-roba-logs")

    started = runtime.require("start")(session="dix")
    owner = json.loads(Path(started["owner_file"]).read_text(encoding="utf-8"))
    assert owner["runtime_root"] == str(root / "run/sessions/dix/roba")
    assert owner["logs_root"] == str(root / "state/sessions/dix/logs")
    assert "/tmp/ambient-roba" not in json.dumps(owner)


def test_runtime_never_adopts_or_stops_a_foreign_daemon(cockpit_runtime) -> None:
    runtime, _, _runtime_object = cockpit_runtime
    paths = runtime.require("paths")(session="dix")
    environment = {
        "ROBA_RUNTIME_ROOT": paths["roba_runtime_root"],
        "ROBA_LOGS_ROOT": paths["roba_logs_root"],
    }
    start_daemon("default", env=environment)
    try:
        status = runtime.require("status")(session="dix")
        assert status["state"] == "foreign"
        with pytest.raises(RuntimeError, match="without Cockpit ownership"):
            runtime.require("start")(session="dix")
        with pytest.raises(RuntimeError, match="without Cockpit ownership"):
            runtime.require("stop")(session="dix")
    finally:
        stop_daemon(daemon="id:default", env=environment)


def test_failed_probe_with_endpoint_evidence_is_uncertain_and_never_mutates(
    cockpit_runtime,
) -> None:
    runtime, root, runtime_object = cockpit_runtime
    paths = runtime.require("paths")(session="dix")
    endpoint = Path(paths["daemon_socket"])
    endpoint.parent.mkdir(parents=True)
    endpoint.write_text("endpoint-evidence", encoding="utf-8")
    owner = Path(paths["owner_file"])
    owner.write_text("owner-evidence", encoding="utf-8")
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    calls: list[str] = []

    def status() -> object:
        calls.append("status")
        raise RuntimeError("secret-status-detail-must-not-escape")

    runtime_object.daemon = FakeApi(
        set=lambda _value: calls.append("set") or True,
        status=status,
        start=lambda: calls.append("start"),
        stop=lambda: calls.append("stop"),
    )

    reported = runtime.require("status")(session="dix")
    assert reported["state"] == "uncertain"
    assert reported["running"] is False
    assert "secret-status-detail" not in json.dumps(reported)
    for operation in ("start", "stop"):
        with pytest.raises(RuntimeError, match="expected runtime endpoints"):
            runtime.require(operation)(session="dix")
    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert "start" not in calls and "stop" not in calls
