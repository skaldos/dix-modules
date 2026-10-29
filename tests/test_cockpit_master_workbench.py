from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


@pytest.fixture
def application(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    app = applications.create_instance(
        ApplicationInstanceSpec(
            "master-workbench", "skaldos/cockpit/master_workbench", {}, tmp_path
        ),
        owner_scope_id="cockpit-master-workbench-test",
    )
    try:
        yield app
    finally:
        applications.destroy_instance(
            "cockpit-master-workbench-test", "master-workbench"
        )
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def _healthy_runtime(secret: str = "private-control-capability") -> FakeApi:
    return FakeApi(
        owner_environment=lambda **_values: {
            "ROBA_DAEMON": "id:default",
            "ROBA_CONTROL": "id:default",
            "ROBA_RUNTIME_ROOT": "/tmp/cockpit/roba",
            "ROBA_LOGS_ROOT": "/tmp/cockpit/logs",
            "ROBA_CONTROL_TOKEN": secret,
        },
        status=lambda **_values: {
            "state": "running",
            "running": True,
            "owned": True,
            "pid": 31415,
        },
        paths=lambda **_values: {
            "daemon_socket": "/tmp/cockpit/roba/daemon.sock",
            "control_socket": "/tmp/cockpit/roba/control.sock",
        },
    )


def test_master_workbench_materializes_live_capability_only_in_process(application) -> None:
    runtime = application.runtime
    execute = lambda value, object_id=None: []
    calls: list[tuple[object, object, str, bool]] = []
    runtime.runtime = _healthy_runtime()
    runtime.loom = FakeApi(execute=execute)
    runtime.workbench = FakeApi(
        start=lambda *values, **options: calls.append((values, options)) or 0)
    argv = ["--session", "private", "--logo", "roba"]

    assert runtime.main(argv) == 0
    assert len(calls) == 1
    values, options = calls[0]
    assert options == {"show_branding": False}
    bound_execute, seed, logo, confirm = values
    assert bound_execute is execute
    assert seed == {
        "daemon_id": "default",
        "runtime_root": "/tmp/cockpit/roba",
        "logs_root": "/tmp/cockpit/logs",
        "timeout": 5.0,
        "pid": 31415,
        "daemon_socket": "/tmp/cockpit/roba/daemon.sock",
        "control_socket": "/tmp/cockpit/roba/control.sock",
        "control_token": "private-control-capability",
    }
    assert logo == "roba"
    assert confirm is True
    assert "private-control-capability" not in " ".join(argv)


def test_master_workbench_graph_uses_only_existing_runtime_loom_and_workbench(
    application,
) -> None:
    assert {
        instance.definition_id for instance in application.compositions.values()
    } == {
        "skaldos/cockpit/roba_runtime",
        "skaldos/visidata/loom_workbench",
        "dix/roba/loom",
    }


@pytest.mark.parametrize(
    ("owner", "status", "paths", "expected"),
    (
        (RuntimeError("not running"), None, None, "not running"),
        (
            {"ROBA_CONTROL_TOKEN": "secret", "ROBA_DAEMON": "id:other"},
            None,
            None,
            "unexpected daemon locator",
        ),
        (
            {
                "ROBA_CONTROL_TOKEN": "secret",
                "ROBA_DAEMON": "id:default",
                "ROBA_RUNTIME_ROOT": "/tmp/run",
                "ROBA_LOGS_ROOT": "/tmp/logs",
            },
            {"state": "drift", "owned": False, "pid": 1},
            {"daemon_socket": "/tmp/d", "control_socket": "/tmp/c"},
            "not healthy",
        ),
    ),
)
def test_unhealthy_runtime_fails_before_visidata_and_redacts_capability(
    application,
    capsys,
    owner,
    status,
    paths,
    expected: str,
) -> None:
    runtime = application.runtime

    def owner_environment(**_values):
        if isinstance(owner, Exception):
            raise owner
        return owner

    runtime.runtime = FakeApi(
        owner_environment=owner_environment,
        status=lambda **_values: status,
        paths=lambda **_values: paths,
    )
    runtime.workbench = FakeApi(
        start=lambda *_values, **_options: pytest.fail("VisiData must not start")
    )
    assert runtime.main([]) == 2
    error = capsys.readouterr().err
    assert expected in error
    assert "secret" not in error


def test_downstream_error_cannot_echo_owner_capability(application, capsys) -> None:
    secret = "roba-control-private-value"
    runtime = application.runtime
    runtime.runtime = _healthy_runtime(secret)
    runtime.workbench = FakeApi(
        start=lambda *_values, **_options: (_ for _ in ()).throw(
            RuntimeError(f"provider rejected {secret}")
        )
    )
    assert runtime.main([]) == 2
    error = capsys.readouterr().err
    assert "[redacted]" in error
    assert secret not in error


def test_help_and_argument_errors_never_touch_runtime(application, capsys) -> None:
    runtime = application.runtime
    runtime.runtime = FakeApi(
        owner_environment=lambda **_values: pytest.fail("runtime must not be touched")
    )
    assert runtime.main(["--help"]) == 0
    assert "--session" in capsys.readouterr().out
    assert runtime.main(["--logo", "invalid"]) == 2


def test_master_has_no_legacy_store_command_binding_hook(application):
    assert not hasattr(application.runtime, '_bind_store_commands')
