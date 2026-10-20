from __future__ import annotations

import copy
import datetime as dt
import math
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path


@pytest.fixture
def values(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(Path(__file__).parents[1] / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "values", "skaldos/visidata/value_workbench", {}, tmp_path
        ),
        owner_scope_id="visidata-value-test",
    )
    try:
        yield instance.api
    finally:
        compositions.destroy_instance("visidata-value-test", "values")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_draft_navigation_mutations_and_dirty_state(values) -> None:
    source = {
        "project": {"name": "dix", "flags": [True, False]},
        "numbers": [1, 3],
    }
    original = copy.deepcopy(source)
    draft = values.require("create_draft")(source)

    assert draft.at(("project", "name")) == "dix"
    detached = draft.at(("project",))
    detached["name"] = "outside"
    source["project"]["name"] = "source-mutated"
    assert draft.value == original
    assert draft.dirty is False

    draft.replace(("project", "name"), "roba")
    draft.add_mapping(("project",), "count", 2)
    draft.rename_mapping(("project",), "count", "workers")
    draft.delete_mapping(("project",), "workers")
    draft.insert_list(("numbers",), 1, 2)
    draft.append_list(("numbers",), 4)
    draft.delete_list(("numbers",), 0)

    assert draft.value == {
        "project": {"name": "roba", "flags": [True, False]},
        "numbers": [2, 3, 4],
    }
    assert draft.dirty is True
    assert source["project"]["name"] == "source-mutated"


def test_register_is_deeply_isolated_and_supports_all_put_forms(values) -> None:
    draft = values.require("create_draft")({
        "source": {"nested": [1]},
        "replacement": None,
        "mapping": {},
        "items": [],
    })

    draft.copy_to_register(("source",))
    draft.value["source"]["nested"].append(2)
    exported = draft.register_value()
    exported["nested"].append(99)

    draft.put_replacement(("replacement",))
    draft.put_mapping(("mapping",), "copied")
    draft.put_list(("items",))
    draft.put_list(("items",), 0)

    expected = {"nested": [1]}
    assert draft.value["replacement"] == expected
    assert draft.value["mapping"] == {"copied": expected}
    assert draft.value["items"] == [expected, expected]
    assert draft.value["replacement"] is not draft.value["mapping"]["copied"]
    assert draft.value["items"][0] is not draft.value["items"][1]
    assert draft.register_value() == expected


@pytest.mark.parametrize(
    "operation",
    [
        lambda draft: draft.replace(("missing",), 1),
        lambda draft: draft.add_mapping(("items",), "key", 1),
        lambda draft: draft.add_mapping(("mapping",), "", 1),
        lambda draft: draft.add_mapping(("mapping",), "present", 2),
        lambda draft: draft.rename_mapping(("mapping",), "absent", "new"),
        lambda draft: draft.rename_mapping(("mapping",), "present", "other"),
        lambda draft: draft.delete_mapping(("mapping",), "absent"),
        lambda draft: draft.insert_list(("items",), 2, 1),
        lambda draft: draft.delete_list(("items",), 1),
    ],
)
def test_failed_structural_operations_are_atomic(values, operation) -> None:
    draft = values.require("create_draft")({
        "mapping": {"present": 1, "other": 2},
        "items": [0],
    })
    draft.copy_to_register(("mapping", "present"))
    before = copy.deepcopy(draft.value)
    register = draft.register_value()

    with pytest.raises((TypeError, ValueError, KeyError, IndexError)):
        operation(draft)

    assert draft.value == before
    assert draft.register_value() == register


def test_empty_register_and_failed_literal_leave_draft_unchanged(values) -> None:
    draft = values.require("create_draft")({"value": 1})
    before = copy.deepcopy(draft.value)
    with pytest.raises(ValueError, match="register is empty"):
        draft.put_replacement(("value",))
    with pytest.raises(ValueError, match="invalid TOML literal"):
        values.require("parse_toml_literal")("[not valid")
    assert draft.value == before
    assert draft.dirty is False


def test_toml_literals_preserve_native_scalar_and_container_types(values) -> None:
    parse = values.require("parse_toml_literal")
    assert parse('"hello"') == "hello"
    assert parse("true") is True
    assert parse("42") == 42
    assert parse("1.5") == 1.5
    assert math.isnan(parse("nan"))
    assert parse("1979-05-27") == dt.date(1979, 5, 27)
    assert parse("07:32:00") == dt.time(7, 32)
    assert parse("1979-05-27T07:32:00Z") == dt.datetime(
        1979, 5, 27, 7, 32, tzinfo=dt.UTC
    )
    assert parse("[1, 2]") == [1, 2]
    assert parse("{ name = 'dix', enabled = true }") == {
        "name": "dix",
        "enabled": True,
    }
    with pytest.raises(ValueError, match="exactly one"):
        parse("1\nother = 2")


def test_unchanged_nested_nan_is_semantically_clean(values) -> None:
    draft = values.require("create_draft")({"values": [float("nan"), {"n": float("nan")}]})
    assert draft.dirty is False
    draft.replace(("values", 0), float("nan"))
    assert draft.dirty is False
    draft.replace(("values", 0), 1.0)
    assert draft.dirty is True
