from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
sys.path.insert(0, str(DIX / "src"))


@pytest.fixture
def load_runtime():
    def load(relative: str):
        path = ROOT / relative
        name = "test_" + relative.replace("/", "_").replace(".", "_")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.Runtime

    return load


class Api:
    def __init__(self, **functions):
        self.functions = functions

    def require(self, name):
        return self.functions[name]


@pytest.fixture
def api():
    return Api


@pytest.fixture
def store_graph(monkeypatch):
    import shutil
    import tempfile

    from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
    from dix.core.composition import CompositionInstanceSpec
    from dix.modules import first_party_module_path

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
