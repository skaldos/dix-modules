from __future__ import annotations

import sys
from pathlib import Path

from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[2]


class DataspaceGraph:
    """Explicit test/integration graph; native loader lifecycle, no sys.modules cleanup."""

    def __init__(self, fixtures=None, *, modules_root=ROOT, roba=False):
        self._before = set(sys.modules)
        self._registry = create_core_component_registry()
        self._modules = self._registry.require("module", ModuleComponent)
        self._comps = self._registry.require("composition", CompositionComponent)
        self._loaded, self._instances = [], []
        try:
            for name in (("dix/state", "dix/cli", "dix/norn", "dix/roba") if roba else ("dix/norn",)):
                self._modules.load_module(first_party_module_path(name), module_id=name)
                self._loaded.append(name)
            for relative, name in [("stores/nolspace/core", "skaldos/stores/nolspace/core"),
                                   ("stores/dataspace/core", "skaldos/stores/dataspace/core")]:
                self._modules.load_module(modules_root / relative, module_id=name)
                self._loaded.append(name)
            if roba:
                name = "skaldos/stores/nolspace/roba"
                self._modules.load_module(modules_root / "stores/nolspace/roba", module_id=name)
                self._loaded.append(name)
            name = "local/dataspace"
            self._modules.load_module(fixtures or modules_root / "tests/fixtures/dataspace", module_id=name)
            self._loaded.append(name)
        except BaseException:
            self.close()
            raise

    def create(self, use="local/dataspace/definitions", config=None, base=None):
        ident = "d" + str(len(self._instances))
        instance = self._comps.create_instance(
            CompositionInstanceSpec(ident, use, config or {}, base or ROOT), owner_scope_id="dataspace")
        self._instances.append(ident)
        return instance.api

    def close(self):
        for ident in reversed(self._instances):
            self._comps.destroy_instance("dataspace", ident)
        for name in reversed(self._loaded):
            self._modules.unload_module(name)
        new_names = set(sys.modules) - self._before
        assert not any(name.startswith(("_dix_composition_", "_dix_application_")) for name in new_names)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
