from __future__ import annotations

import copy
import datetime as dt
import importlib
import math
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


def test_nested_toml_edit_flow_is_detached_native_and_source_read_only(
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
    source = tmp_path / "nested.toml"
    source.write_text(
        """
name = "dix"
enabled = true
count = 3
ratio = 1.5
special = nan
date = 1979-05-27
time = 07:32:00
stamp = 1979-05-27T07:32:00Z
items = [1, 3]

[nested]
mode = "local"
""".lstrip()
    )
    before_bytes = source.read_bytes()
    before_names = {path.name for path in tmp_path.iterdir()}

    assert app.api.require("main")(["--file", str(source)]) == 0
    draft = seen[0].draft
    assert draft.dirty is False
    assert math.isnan(draft.value["special"])
    assert draft.value["date"] == dt.date(1979, 5, 27)
    assert draft.value["time"] == dt.time(7, 32)
    assert draft.value["stamp"] == dt.datetime(1979, 5, 27, 7, 32, tzinfo=dt.UTC)

    draft.replace(("name",), "roba")
    draft.add_mapping(("nested",), "new", False)
    draft.rename_mapping(("nested",), "new", "renamed")
    draft.delete_mapping(("nested",), "renamed")
    draft.insert_list(("items",), 1, 2)
    draft.append_list(("items",), 4)
    draft.delete_list(("items",), 0)
    draft.copy_to_register(("nested",))
    draft.put_mapping((), "copied")
    draft.put_list(("items",))
    draft.put_replacement(("copied",))
    assert draft.dirty is True
    assert draft.value["items"][:3] == [2, 3, 4]
    assert draft.value["items"][3] == {"mode": "local"}
    assert draft.value["copied"] == {"mode": "local"}

    draft_before_error = copy.deepcopy(draft.value)
    register_before_error = draft.register_value()
    with pytest.raises(ValueError):
        draft.add_mapping(("nested",), "mode", "collision")
    assert draft.value == draft_before_error
    assert draft.register_value() == register_before_error
    assert source.read_bytes() == before_bytes
    assert {path.name for path in tmp_path.iterdir()} == before_names


def test_local_workbench_branding_keeps_both_reviewed_assets(application) -> None:
    _app, registry = application
    runtime = next(
        instance.runtime
        for instance in registry.require("composition", CompositionComponent).instances()
        if instance.definition_id == "skaldos/visidata/value_workbench"
    )
    package = importlib.import_module(runtime.__class__.__module__).__package__
    branding = importlib.import_module(f"{package}.branding")
    for logo in ("dix", "roba"):
        command = branding.logo_command(logo)
        assert command[:7] == ["chafa", "--fill", "block", "-c", "full", "--scale", "0.5"]
        assert Path(command[7]).is_file()
