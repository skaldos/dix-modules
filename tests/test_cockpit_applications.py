from __future__ import annotations

import importlib
import os
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import (
    ApplicationComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


@pytest.fixture
def applications(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    apps = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    created = {}
    for name in ("cli", "control_window", "connection_window"):
        created[name] = apps.create_instance(
            ApplicationInstanceSpec(name, f"skaldos/cockpit/{name}", {}, tmp_path),
            owner_scope_id="cockpit-app-test",
        )
    try:
        yield created
    finally:
        for name in reversed(tuple(created)):
            apps.destroy_instance("cockpit-app-test", name)
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_cli_start_builds_only_non_secret_window_commands(
    applications, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = applications["cli"].runtime
    catalog = tmp_path / "daemons.toml"
    catalog.write_text(
        '[daemons.local]\ndaemon_id="d"\nruntime_root="/tmp/r"\nlogs_root="/tmp/l"\n'
    )
    captured: dict[str, object] = {}

    def start(**values):
        captured.update(values)
        return {"created": True}

    runtime.settings = FakeApi(catalog_path=lambda value=None: Path(value or catalog))
    runtime.catalog = FakeApi(load=lambda _path: [{"catalog_id": "local"}])
    runtime.session = FakeApi(start=start)
    monkeypatch.setenv("DIX_BIN", str(tmp_path / "bin"))
    assert runtime.main(["start", "--catalog", str(catalog), "--logo", "roba"]) == 0
    assert captured["attach"] is True
    assert captured["count"] == 1
    joined = " ".join((*captured["control_command"], *captured["header_command"]))
    assert str(catalog) in joined and "roba" in joined
    assert "token" not in joined.lower()


def test_cli_status_and_stop_are_scriptable_without_start(applications, capsys) -> None:
    runtime = applications["cli"].runtime
    runtime.session = FakeApi(
        status=lambda **_values: {
            "session": "dix",
            "socket": "/tmp/dix-cockpit/tmux.sock",
            "running": False,
            "windows": [],
        },
        stop=lambda **_values: False,
    )
    assert runtime.main(["status"]) == 1
    assert '"running":false' in capsys.readouterr().out
    assert runtime.main(["stop"]) == 0
    assert '"stopped": false' in capsys.readouterr().out


def test_connection_window_resolves_catalog_identity_before_starting_workbench(
    applications, tmp_path: Path
) -> None:
    runtime = applications["connection_window"].runtime
    catalog = tmp_path / "daemons.toml"
    catalog.write_text("placeholder")
    seed = {
        "daemon_id": "d",
        "runtime_root": "/tmp/r",
        "logs_root": "/tmp/l",
        "timeout": 5.0,
        "control_token": "local-only-secret",
    }
    workbench_calls: list[tuple[object, object, str, bool]] = []
    execute = lambda value, object_id=None: []
    runtime.catalog = FakeApi(load=lambda _path: [{"catalog_id": "local"}])
    runtime.connections = FakeApi(
        resolve=lambda _entry: {"state": "running", "connection": seed, "error": None}
    )
    runtime.loom = FakeApi(execute=execute)
    runtime.workbench = FakeApi(
        start=lambda *values: workbench_calls.append(values) or 0,
    )
    arguments = ["--catalog", str(catalog), "--catalog-id", "local", "--logo", "dix"]
    assert runtime.main(arguments) == 0
    assert workbench_calls == [(execute, seed, "dix", True)]
    assert "local-only-secret" not in " ".join(arguments)


def test_connection_error_remains_visible_and_does_not_start_workbench(
    applications, tmp_path: Path, capsys
) -> None:
    runtime = applications["connection_window"].runtime
    runtime.catalog = FakeApi(load=lambda _path: [{"catalog_id": "broken"}])
    runtime.connections = FakeApi(
        resolve=lambda _entry: {
            "state": "error",
            "connection": None,
            "error": "control socket rejected credentials",
        }
    )
    runtime.workbench = FakeApi(start=lambda *_values: pytest.fail("must not start"))
    path = tmp_path / "catalog.toml"
    assert runtime.main(["--catalog", str(path), "--catalog-id", "broken"]) == 2
    assert "control socket rejected credentials" in capsys.readouterr().err


def test_header_falls_back_without_chafa(applications, tmp_path: Path, monkeypatch, capsys) -> None:
    runtime = applications["control_window"].runtime
    monkeypatch.setenv("DIX_COCKPIT_ASSET_ROOT", str(tmp_path / "missing"))
    assert runtime.main(
        [
            "--mode",
            "header",
            "--once",
            "--session",
            "demo",
            "--catalog",
            str(tmp_path / "catalog.toml"),
            "--logo",
            "dix",
        ]
    ) == 0
    assert "DIX Cockpit | session demo" in capsys.readouterr().out


@pytest.mark.parametrize("logo", ("dix", "roba"))
def test_header_selects_existing_logo_with_optional_chafa(
    applications, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logo: str
) -> None:
    runtime = applications["control_window"].runtime
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    log = tmp_path / f"{logo}.log"
    chafa = tools / "chafa"
    chafa.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" > "{log}"\n')
    chafa.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    monkeypatch.setenv("DIX_COCKPIT_ASSET_ROOT", str(ROOT / "visidata/assets"))
    assert runtime.main(
        [
            "--mode",
            "header",
            "--once",
            "--session",
            "demo",
            "--catalog",
            str(tmp_path / "catalog.toml"),
            "--logo",
            logo,
        ]
    ) == 0
    assert str(ROOT / f"visidata/assets/{logo}.png") in log.read_text()


def test_application_graph_is_static_and_reuses_generic_workbench(applications) -> None:
    connection = applications["connection_window"]
    with (ROOT / "cockpit/apps/connection_window/app.toml").open("rb") as source:
        definition = tomllib.load(source)
    assert {dependency["use"] for dependency in definition["compositions"].values()} == {
        "skaldos/cockpit/daemon_catalog",
        "skaldos/cockpit/roba_connections",
        "skaldos/visidata/loom_workbench",
        "dix/roba/loom",
    }
    module = importlib.import_module(connection.runtime.__class__.__module__)
    source = Path(module.__file__).read_text()
    assert "subprocess" not in source
    assert "dix-roba-cli" not in source
