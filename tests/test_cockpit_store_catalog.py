from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


@pytest.fixture
def store_graph(monkeypatch):
    root = Path(tempfile.mkdtemp(prefix="s65-"))
    monkeypatch.setenv("DIX_COCKPIT_RUNTIME_ROOT", str(root / "r"))
    monkeypatch.setenv("DIX_COCKPIT_STATE_ROOT", str(root / "s"))
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    comp = registry.require("composition", CompositionComponent)
    loaded = []
    instances = []
    for name in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(name), module_id=name)
        loaded.append(name)
    for name in ("visidata", "cockpit"):
        modules.load_module(ROOT / name, module_id=f"skaldos/{name}")
        loaded.append(f"skaldos/{name}")

    def create(use):
        ident = f"s{len(instances)}"
        instance = comp.create_instance(
            CompositionInstanceSpec(ident, use, {}, ROOT), owner_scope_id="store-test")
        instances.append(ident)
        return instance

    runtime = create("skaldos/cockpit/roba_runtime").api
    runtime.require("start")(session="a")
    try:
        yield create, runtime, root
    finally:
        for name in ("a", "b"):
            runtime.require("stop")(session=name)
        for ident in reversed(instances):
            comp.destroy_instance("store-test", ident)
        for name in reversed(loaded):
            modules.unload_module(name)
        shutil.rmtree(root)


def test_catalog_bootstrap_crud_session_isolation_and_reset(store_graph, api):
    create, runtime, root = store_graph
    target_calls = []

    def validate(value):
        assert isinstance(value, dict) and set(value) == {"address"}
        return value

    provider = api(draft=lambda: {"address": ""}, validate=validate,
                   root=lambda *_: target_calls.append("root"), children=lambda *_: None,
                   inspect=lambda *_: None)
    catalog = create("skaldos/cockpit/store_catalog").api
    catalog.require("register_provider")("test", provider)
    assert catalog.require("providers_list")() == ["test"]
    assert catalog.require("list")("a") == []
    assert catalog.require("list")("a") == []
    entry = catalog.require("draft")("test")
    entry["store_id"] = "my store"
    entry["connection"]["address"] = "unreachable"
    catalog.require("create")(entry, "a")
    before = catalog.require("list")("a")
    assert before == [entry]
    entry["connection"]["address"] = "edited"
    catalog.require("update")("my store", entry, "a")
    entry["store_id"] = "renamed"
    catalog.require("update")("my store", entry, "a")
    assert catalog.require("get")("renamed", "a") == entry
    assert before[0]["connection"]["address"] == "unreachable"
    runtime.require("start")(session="b")
    assert catalog.require("list")("b") == []
    other = create("skaldos/cockpit/store_catalog").api
    assert other.require("get")("renamed", "a") == entry
    catalog.require("remove")("renamed", "a")
    assert catalog.require("list")("a") == []
    catalog.require("create")(entry, "a")
    runtime.require("stop")(session="a")
    runtime.require("start")(session="a")
    assert catalog.require("list")("a") == []
    assert target_calls == []
    # No catalog snapshot or credential file was produced.
    assert set((root / "r/sessions/a").iterdir()) == {
        root / "r/sessions/a/roba", root / "r/sessions/a/owner.json",
        root / "r/sessions/a/stores.lock"}


def test_catalog_invalid_requests_do_not_change_state(store_graph, api):
    create, _, _ = store_graph
    catalog = create("skaldos/cockpit/store_catalog").api

    def validate(value):
        if value != {"x": "secret"}:
            raise ValueError("invalid provider draft")
        return value

    catalog.require("register_provider")("test", api(
        draft=lambda: {"x": ""}, validate=validate, root=lambda *_: None,
        children=lambda *_: None, inspect=lambda *_: None))
    entry = {"store_id": "ok", "provider": "test", "connection": {"x": "secret"}}
    catalog.require("create")(entry, "a")
    before = json.dumps(catalog.require("list")("a"), sort_keys=True)
    for value in (entry, {**entry, "store_id": ""}, {**entry, "provider": "bad"},
                  {**entry, "connection": {}}, {**entry, "extra": True}):
        with pytest.raises(ValueError):
            catalog.require("create")(value, "a")
    with pytest.raises(ValueError):
        catalog.require("update")("missing", entry, "a")
    with pytest.raises(ValueError):
        catalog.require("remove")("missing", "a")
    with pytest.raises(ValueError):
        catalog.require("provider_call")("test", "write", {})
    assert json.dumps(catalog.require("list")("a"), sort_keys=True) == before
