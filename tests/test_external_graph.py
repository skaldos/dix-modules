from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import i3ipc
from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path


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


def test_stateless_navigation_compositions_run_in_real_dix_graph(tmp_path, monkeypatch):
    class NavigatingConnection(Connection):
        focused = 34

        def command(self, value):
            if value == "focus right":
                type(self).focused = 32
            elif value.startswith("[con_id="):
                type(self).focused = int(value.split("=", 1)[1].split("]", 1)[0])
            return [Reply()]

    monkeypatch.setattr(i3ipc, "Connection", NavigatingConnection)
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    applications = registry.require("application", ApplicationComponent)
    root = Path(__file__).parents[1] / "sway"
    modules.load_module(first_party_module_path("dix/cli"), module_id="dix/cli")
    modules.load_module(root / "core", module_id="skaldos/sway/core")
    modules.load_module(root / "nav", module_id="skaldos/sway/nav")

    basic = compositions.create_instance(
        CompositionInstanceSpec("basic", "skaldos/sway/nav/basic_nav", {}, tmp_path),
        owner_scope_id="navigation-proof",
    )
    assert basic.api.require("right")() == {
        "direction": "right",
        "origin_id": 34,
        "focused_id": 32,
        "changed": True,
    }

    NavigatingConnection.focused = 34
    window_list = compositions.create_instance(
        CompositionInstanceSpec(
            "window-list", "skaldos/sway/nav/windows_list_nav", {}, tmp_path
        ),
        owner_scope_id="navigation-proof",
    )
    result = window_list.api.require("right")([32, 392])
    assert result["matched"] is True
    assert result["focused_id"] == 32
    assert result["visited_ids"] == [34, 32]

    NavigatingConnection.focused = 34
    nav = applications.create_instance(
        ApplicationInstanceSpec("nav", "skaldos/sway/nav/nav", {}, tmp_path),
        owner_scope_id="navigation-proof",
    )
    assert nav.api.require("right")("basic")["focused_id"] == 32
    NavigatingConnection.focused = 34
    routed = nav.api.require("right")("windows-list", [32, 392])
    assert routed["matched"] is True
    assert routed["focused_id"] == 32
    applications.destroy_instance("navigation-proof", "nav")

    compositions.destroy_instance("navigation-proof", "window-list")
    compositions.destroy_instance("navigation-proof", "basic")
    modules.unload_module("skaldos/sway/nav")
    modules.unload_module("skaldos/sway/core")
    modules.unload_module("dix/cli")
