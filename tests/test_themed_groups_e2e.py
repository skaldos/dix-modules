from __future__ import annotations

import json
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import ClassVar

import i3ipc
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path
from roba import RobaClient, stop_daemon

ROOT = Path(__file__).parents[1]


class Node:
    def __init__(self, value: int) -> None:
        self.id = value


class Reply:
    success = True
    error = None


class Connection:
    focused = 34
    live: ClassVar[list[int]] = [34, 32, 392]
    commands: ClassVar[list[str]] = []
    marker: ClassVar[Path | None] = None

    def get_tree(self):
        return self

    def find_focused(self):
        return Node(self.focused)

    def leaves(self):
        return [Node(value) for value in self.live]

    def command(self, value):
        if self.marker is not None:
            assert not self.marker.exists(), "theme marker was written before IPC completed"
        self.commands.append(value)
        return [Reply()]


def _definition(path: Path, group: str, theme: str) -> None:
    path.write_text(f"group = {group!r}\ntheme = {theme!r}\n", encoding="utf-8")


def test_manifest_keeps_files_groups_and_themes_as_the_only_dependencies() -> None:
    manifest = tomllib.loads((ROOT / "sway/apps/themed_groups/app.toml").read_text())

    assert manifest["compositions"] == {
        "themed_group_files": {"use": "skaldos/sway/themed_group_files"}
    }
    assert manifest["apps"] == {
        "groups": {"use": "skaldos/sway/groups"},
        "themes": {"use": "skaldos/sway/themes"},
    }
    assert set(manifest["functions"]) == {"list", "load", "select"}


def test_real_dix_roba_fake_sway_themed_groups_graph(tmp_path, monkeypatch):
    short_home = Path(tempfile.mkdtemp(prefix="tg-", dir="/tmp"))
    state_file = tmp_path / "state/groups.json"
    members_file = tmp_path / "state/active-members"
    target_file = tmp_path / "state/navigation-target"
    marker = tmp_path / "state/active-theme"
    theme_dir = tmp_path / "themes"
    definition_dir = tmp_path / "themed-groups"
    shutil.copytree(ROOT / "sway/integrations/themes", theme_dir)
    definition_dir.mkdir()
    _definition(definition_dir / "dix.toml", "dix-dev", "dix")
    _definition(definition_dir / "roba.toml", "roba-dev", "roba")

    Connection.focused = 34
    Connection.live = [34, 32, 392]
    Connection.commands = []
    Connection.marker = marker
    monkeypatch.setattr(i3ipc, "Connection", Connection)
    monkeypatch.setenv("HOME", str(short_home))
    monkeypatch.setenv("SKALDOS_SWAY_GROUP_STATE_FILE", str(state_file))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE", str(members_file))
    monkeypatch.setenv("SKALDOS_SWAY_NAVIGATION_TARGET_FILE", str(target_file))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_THEME_FILE", str(marker))
    monkeypatch.setenv("SKALDOS_SWAY_THEME_DIR", str(theme_dir))
    monkeypatch.setenv("SKALDOS_SWAY_THEMED_GROUP_DIR", str(definition_dir))

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    created: list[tuple[str, str]] = []
    daemon_started = False
    cleanup_errors: list[Exception] = []
    owner = "themed-groups-e2e"
    try:
        for module_id in ("dix/state", "dix/cli", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(ROOT / "sway", module_id="skaldos/sway")
        loaded.append("skaldos/sway")

        managed = applications.create_instance(
            ApplicationInstanceSpec("managed", "dix/roba/managed", {}, tmp_path),
            owner_scope_id=owner,
        )
        created.append((owner, "managed"))
        managed.api.require("start")()
        daemon_started = True

        control = applications.create_instance(
            ApplicationInstanceSpec("control", "dix/roba/control", {}, tmp_path),
            owner_scope_id=owner,
        )
        created.append((owner, "control"))
        control.api.require("create_context")(context_id="skaldos-sway")

        groups = applications.create_instance(
            ApplicationInstanceSpec("groups", "skaldos/sway/groups", {}, tmp_path),
            owner_scope_id=owner,
        )
        created.append((owner, "groups"))
        groups.api.require("create")("dix-dev")
        groups.api.require("add")("dix-dev")
        groups.api.require("create")("foreign")
        Connection.focused = 32
        groups.api.require("add")("foreign")
        assert groups.api.require("select")("dix-dev") is True
        assert members_file.read_bytes() == b"34\n"

        themed_groups = applications.create_instance(
            ApplicationInstanceSpec(
                "themed-groups", "skaldos/sway/themed_groups", {}, tmp_path
            ),
            owner_scope_id=owner,
        )
        created.append((owner, "themed-groups"))

        assert themed_groups.api.require("list")() == {
            "dix-dev": "dix",
            "roba-dev": "roba",
        }
        assert themed_groups.api.require("load")() == {
            "managed_groups": ["dix-dev", "roba-dev"],
            "created_groups": ["roba-dev"],
            "cleared_groups": ["dix-dev"],
            "deactivated": True,
        }
        assert json.loads(state_file.read_text()) == {
            "groups": {"dix-dev": [], "foreign": [32], "roba-dev": []},
            "active_group": "",
        }
        assert members_file.read_bytes() == b"\n"
        assert target_file.read_bytes() == b"basic\n"
        assert not marker.exists()

        credentials = control.api.require("context_credentials")(
            context_id="skaldos-sway"
        )
        roba_state = (
            RobaClient(timeout=5)
            .context(
                locator=credentials["context_locator"],
                token=credentials["owner_token"],
            )
            .state()
        )
        assert roba_state == {
            "groups": ["dix-dev", "foreign", "roba-dev"],
            "active_group": "",
        }

        Connection.focused = 392
        assert groups.api.require("add")("dix-dev") is True
        selected = themed_groups.api.require("select")("dix-dev")
        assert selected == {
            "group": "dix-dev",
            "theme": "dix",
            "group_changed": True,
            "theme_result": {
                "theme": "dix",
                "path": str((theme_dir / "dix.toml").resolve()),
                "background": "image",
            },
        }
        assert json.loads(state_file.read_text()) == {
            "groups": {"dix-dev": [392], "foreign": [32], "roba-dev": []},
            "active_group": "dix-dev",
        }
        assert members_file.read_bytes() == b"392\n"
        assert target_file.read_bytes() == b"group\n"
        assert marker.read_bytes() == b"dix\n"
        wallpaper = (theme_dir / "wallpapers/dix.png").resolve()
        assert Connection.commands == [
            "client.focused #D85A96 #4A1735 #FFF4E8 #FF2E88 #B52A68",
            "client.focused_inactive #743250 #2E1826 #E8CFDA #92516E #5C263F",
            "client.focused_tab_title #8A3A5D #351C2C #F5DDE8",
            "client.unfocused #402231 #171014 #BBA6AF #603248 #2D1923",
            "client.urgent #FFB000 #5B2200 #FFF7E0 #FF6A00 #FFB000",
            f"output * bg {json.dumps(str(wallpaper))} fit #10080E",
        ]
        assert (
            RobaClient(timeout=5)
            .context(
                locator=credentials["context_locator"],
                token=credentials["owner_token"],
            )
            .state()
            == {
                "groups": ["dix-dev", "foreign", "roba-dev"],
                "active_group": "dix-dev",
            }
        )
    finally:
        for scope, instance in reversed(created):
            try:
                applications.destroy_instance(scope, instance)
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
        if daemon_started:
            try:
                stop_daemon(daemon="id:default")
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
        for module_id in reversed(loaded):
            try:
                modules.unload_module(module_id)
            except Exception as exc:  # noqa: BLE001
                cleanup_errors.append(exc)
        shutil.rmtree(short_home, ignore_errors=True)
        Connection.marker = None
        if cleanup_errors:
            raise ExceptionGroup("themed-groups E2E cleanup failed", cleanup_errors)
