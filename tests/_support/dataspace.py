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
            if roba:
                name = "local/dataspace_roba"
                self._modules.load_module(modules_root / "tests/fixtures/dataspace_roba", module_id=name)
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


class RobaScenario:
    """Caller-owned native bootstrap for tests/manual Python, not a product runtime feature."""

    def __init__(self, graph):
        import shutil
        import tempfile

        from roba import RobaClient, create_context, start_daemon, stop_daemon

        self._shutil, self._stop = shutil, stop_daemon
        self.root = Path(tempfile.mkdtemp(prefix="d74-", dir="/tmp"))
        self.env = {"ROBA_RUNTIME_ROOT": str(self.root / "r"), "ROBA_LOGS_ROOT": str(self.root / "l")}
        self.daemon = None
        try:
            self.daemon = start_daemon("data", env=self.env)
            connections = []
            for context_id in ("session", "projects"):
                created = create_context(context_id=context_id, control=str(self.daemon.control_locator),
                                         control_token=self.daemon.control_token, env=self.env)
                owner = RobaClient(env={}).context(locator=str(created.direct_locator), token=created.owner_token)
                connections.append((owner, {"context_id": context_id,
                    "context_locator": str(created.direct_locator), "token": created.owner_token, "timeout": 2.0}))
            (self.session, self.session_connection), (self.projects, self.project_connection) = connections
            for name in ("private", "evia"):
                self.projects.instance_create(instance_id=name, state={"root": "/projects/" + name})
            self.targets = {name: self.projects.with_scope("id:" + name) for name in ("private", "evia")}
            connection = graph.create("skaldos/stores/nolspace/roba/connection")
            provider = graph.create("skaldos/stores/nolspace/roba/provider")
            self.session_view = provider.lookup(connection.root(self.session_connection), "values")
            self.project_views = {name: connection.root({**self.project_connection, "instance_id": name})
                                  for name in ("private", "evia")}
            self.owner = graph.create("local/dataspace_roba/consumer")
            self.private = self.owner.materialize(self.mounts("private"))
            self.evia = self.owner.materialize(self.mounts("evia"))
        except BaseException:
            self.close()
            raise

    def mounts(self, project="private"):
        return [{"set": "session", "provider_alias": "roba", "nolspace_view": self.session_view},
                {"set": "project", "provider_alias": "roba", "nolspace_view": self.project_views[project]}]

    def close(self):
        import os
        import time

        if self.daemon is not None:
            self._stop(daemon="id:data", env=self.env)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    state = Path(f"/proc/{self.daemon.pid}/stat").read_text().split(") ", 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Owned ROBA process remained alive after stop")
            assert not list(self.root.rglob("*.sock")), "Owned sockets remain after stop"
            self.daemon = None
        self._shutil.rmtree(self.root)
        assert not os.path.exists(self.root)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
