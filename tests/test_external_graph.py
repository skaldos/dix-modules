from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import ClassVar

import i3ipc
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path
from roba import stop_daemon


class Node:
    def __init__(self, value):
        self.id = value


class Reply:
    success = True
    error = None


class Connection:
    focused = 34
    live: ClassVar[list[int]] = [34, 32, 392]

    def get_tree(self):
        return self

    def find_focused(self):
        return Node(self.focused)

    def leaves(self):
        return [Node(v) for v in self.live]

    def command(self, value):
        return [Reply()]


def test_external_provider_real_dix_roba_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(i3ipc, "Connection", Connection)
    short = Path(tempfile.mkdtemp(prefix="sx-", dir="/tmp"))
    monkeypatch.setenv("HOME", str(short))
    monkeypatch.setenv("SKALDOS_SWAY_GROUP_STATE_FILE", str(tmp_path / "groups.json"))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE", str(tmp_path / "members"))
    monkeypatch.setenv("SKALDOS_SWAY_NAVIGATION_TARGET_FILE", str(tmp_path / "target"))
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    apps = registry.require("application", ApplicationComponent)
    loaded = []
    created = []
    for module_id in ("dix/state", "dix/cli", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(Path(__file__).parents[1] / "sway", module_id="skaldos/sway")
    loaded.append("skaldos/sway")
    managed = apps.create_instance(
        ApplicationInstanceSpec("managed", "dix/roba/managed", {}, tmp_path), owner_scope_id="test"
    )
    created.append(("test", "managed"))
    managed.api.require("start")()
    try:
        control = apps.create_instance(
            ApplicationInstanceSpec("control", "dix/roba/control", {}, tmp_path),
            owner_scope_id="test",
        )
        created.append(("test", "control"))
        control.api.require("create_context")(context_id="skaldos-sway")
        groups = apps.create_instance(
            ApplicationInstanceSpec("groups", "skaldos/sway/groups", {}, tmp_path),
            owner_scope_id="test",
        )
        created.append(("test", "groups"))
        groups.api.require("create")("work")
        groups.api.require("add")("work")
        assert groups.api.require("select")("work") is True
        assert (tmp_path / "members").read_text() == "34\n"
        assert (tmp_path / "target").read_text() == "group\n"
        credentials = control.api.require("context_credentials")(context_id="skaldos-sway")
        from roba import RobaClient

        state = (
            RobaClient(timeout=5)
            .context(locator=credentials["context_locator"], token=credentials["owner_token"])
            .state()
        )
        assert state == {"groups": ["work"], "active_group": "work"}
    finally:
        stop_daemon(daemon="id:default")
        shutil.rmtree(short, ignore_errors=True)
