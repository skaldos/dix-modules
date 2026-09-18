from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import i3ipc
import pytest
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path


class Node:
    def __init__(self, value: int):
        self.id = value


class Reply:
    success = True
    error = None


class Connection:
    focused = 34
    commands: ClassVar[list[str]] = []

    def get_tree(self):
        return self

    def find_focused(self):
        return Node(type(self).focused)

    def leaves(self):
        return [Node(value) for value in (34, 23, 42)]

    def command(self, value: str):
        type(self).commands.append(value)
        if value.startswith("focus "):
            type(self).focused = 23
        elif value.startswith("[con_id="):
            type(self).focused = int(value.split("=", 1)[1].split("]", 1)[0])
        return [Reply()]


@pytest.fixture
def cli(tmp_path, monkeypatch):
    Connection.focused = 34
    Connection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", Connection)

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    root = Path(__file__).parents[1] / "sway"
    modules.load_module(first_party_module_path("dix/cli"), module_id="dix/cli")
    modules.load_module(root / "core", module_id="skaldos/sway/core")
    modules.load_module(root / "nav", module_id="skaldos/sway/nav")
    instance = applications.create_instance(
        ApplicationInstanceSpec("cli", "skaldos/sway/nav/cli", {}, tmp_path),
        owner_scope_id="navigation-cli-test",
    )
    try:
        yield instance.api.require("main")
    finally:
        applications.destroy_instance("navigation-cli-test", "cli")
        modules.unload_module("skaldos/sway/nav")
        modules.unload_module("skaldos/sway/core")
        modules.unload_module("dix/cli")


@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
def test_basic_cli_exposes_parameter_free_navigation(cli, capsys, direction):
    assert cli(["basic", direction]) == 0
    value = capsys.readouterr()
    assert f"'direction': '{direction}'" in value.out
    assert value.err == ""
    assert Connection.commands == [f"focus {direction}"]


def test_basic_cli_sets_runtime_binding(cli, capsys):
    assert cli(["basic", "set"]) == 0
    assert capsys.readouterr().out == ""
    assert Connection.commands == ["set $dix_sway_nav basic"]


def test_windows_list_cli_repeats_ids_for_binding(cli, capsys):
    assert cli(["windows-list", "set", "--ids", "23", "--ids", "42"]) == 0
    assert capsys.readouterr().out == ""
    assert Connection.commands == ["set $dix_sway_nav windows-list 23 42"]


def test_windows_list_cli_repeats_ids_for_navigation(cli, capsys):
    assert cli(["windows-list", "right", "--ids", "23", "--ids", "42"]) == 0
    value = capsys.readouterr()
    assert "'matched': True" in value.out
    assert value.err == ""
    assert Connection.commands == ["focus right"]


def test_only_windows_list_accepts_ids(cli, capsys):
    assert cli(["basic", "left", "--ids", "23"]) == 2
    value = capsys.readouterr()
    assert "No such option: --ids" in value.err
    assert Connection.commands == []


def test_cli_help_has_only_two_strategy_targets(cli, capsys):
    assert cli(["--help"]) == 0
    value = capsys.readouterr()
    assert "basic" in value.out and "windows-list" in value.out
    assert "themed-group" not in value.out and "theme" not in value.out
