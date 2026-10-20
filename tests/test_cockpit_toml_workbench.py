from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


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
            "toml-workbench", "skaldos/cockpit/toml_workbench", {}, tmp_path
        ),
        owner_scope_id="cockpit-toml-workbench-test",
    )
    try:
        yield app, registry
    finally:
        applications.destroy_instance("cockpit-toml-workbench-test", "toml-workbench")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_application_loads_once_and_starts_local_workbench(
    application, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from visidata import vd

    app, registry = application
    value_runtime = next(
        instance.runtime
        for instance in registry.require("composition", CompositionComponent).instances()
        if instance.definition_id == "skaldos/visidata/value_workbench"
    )
    package = importlib.import_module(value_runtime.__class__.__module__).__package__
    branding = importlib.import_module(f"{package}.branding")
    seen: list[object] = []
    monkeypatch.setattr(branding, "show_logo", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(vd, "run", lambda sheet: seen.append(sheet))
    source = tmp_path / "config.toml"
    source.write_text('name = "dix"\n[nested]\nvalue = 1\n')
    before = source.read_bytes()

    assert app.api.require("main")(["--file", str(source), "--logo", "roba"]) == 0
    assert len(seen) == 1
    assert seen[0].logo == "roba"
    assert seen[0].draft.value == {"name": "dix", "nested": {"value": 1}}
    seen[0].draft.replace(("nested", "value"), 2)
    assert seen[0].draft.dirty is True
    assert source.read_bytes() == before
    assert {path.name for path in tmp_path.iterdir()} == {"config.toml"}


def test_application_help_and_file_errors_do_not_start_visidata(
    application, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    from visidata import vd

    app, _registry = application
    monkeypatch.setattr(vd, "run", lambda *_args: pytest.fail("VisiData must not start"))
    assert app.api.require("main")(["--help"]) == 0
    assert "--file" in capsys.readouterr().out
    assert app.api.require("main")(["--file", str(tmp_path / "missing.toml")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_application_graph_has_no_roba_or_provider_dependency(application) -> None:
    app, _registry = application
    assert {
        instance.definition_id
        for instance in app.compositions.values()
    } == {
        "skaldos/cockpit/toml_file",
        "skaldos/visidata/value_workbench",
    }
