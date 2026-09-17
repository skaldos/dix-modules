from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

import i3ipc
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class Reply:
    success = True
    error = None


class Connection:
    commands: ClassVar[list[str]] = []

    def command(self, value):
        self.commands.append(value)
        return [Reply()]


def _image_theme(path: Path) -> None:
    path.write_text(
        '''[clients.focused]
border = "#010203"
background = "#040506"
text = "#070809"
indicator = "#0A0B0C"
child_border = "#0D0E0F"

[clients.focused_inactive]
border = "#111213"
background = "#141516"
text = "#171819"
indicator = "#1A1B1C"
child_border = "#1D1E1F"

[clients.focused_tab_title]
border = "#212223"
background = "#242526"
text = "#272829"

[clients.unfocused]
border = "#313233"
background = "#343536"
text = "#373839"
indicator = "#3A3B3C"
child_border = "#3D3E3F"

[clients.urgent]
border = "#414243"
background = "#444546"
text = "#474849"
indicator = "#4A4B4C"
child_border = "#4D4E4F"

[background]
type = "image"
file = "wallpapers/a \\"quoted\\",semi;back\\\\slash.png"
mode = "fill"
fallback_color = "#102030"
'''
    )


def test_real_dix_graph_applies_theme_and_projects_current(
    tmp_path, monkeypatch, capsys
):
    Connection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", Connection)
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    theme_file = theme_dir / "image.toml"
    _image_theme(theme_file)
    marker = tmp_path / "state/active-theme"
    monkeypatch.setenv("SKALDOS_SWAY_THEME_DIR", str(theme_dir))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_THEME_FILE", str(marker))
    monkeypatch.setenv("SKALDOS_SWAY_GROUP_STATE_FILE", str(tmp_path / "groups.json"))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE", str(tmp_path / "members"))
    monkeypatch.setenv("SKALDOS_SWAY_NAVIGATION_TARGET_FILE", str(tmp_path / "target"))

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded = []
    created = []
    try:
        for module_id in ("dix/state", "dix/cli", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(ROOT / "sway", module_id="skaldos/sway")
        loaded.append("skaldos/sway")

        themes = applications.create_instance(
            ApplicationInstanceSpec("themes", "skaldos/sway/themes", {}, ROOT / "sway"),
            owner_scope_id="theme-e2e",
        )
        created.append(("theme-e2e", "themes"))
        result = themes.api.require("apply")("image")

        image = (theme_dir / 'wallpapers/a "quoted",semi;back\\slash.png').resolve()
        assert result == {
            "theme": "image",
            "path": str(theme_file.resolve()),
            "background": "image",
        }
        assert marker.read_bytes() == b"image\n"
        assert Connection.commands == [
            "client.focused #010203 #040506 #070809 #0A0B0C #0D0E0F",
            "client.focused_inactive #111213 #141516 #171819 #1A1B1C #1D1E1F",
            "client.focused_tab_title #212223 #242526 #272829",
            "client.unfocused #313233 #343536 #373839 #3A3B3C #3D3E3F",
            "client.urgent #414243 #444546 #474849 #4A4B4C #4D4E4F",
            f"output * bg {json.dumps(str(image))} fill #102030",
        ]

        cli = applications.create_instance(
            ApplicationInstanceSpec("cli", "skaldos/sway/cli", {}, ROOT / "sway"),
            owner_scope_id="theme-e2e",
        )
        created.append(("theme-e2e", "cli"))
        assert cli.api.require("main")(
            ["theme", "current", "--active_theme_file", str(marker)]
        ) == 0
        assert capsys.readouterr().out.strip() == "image"
    finally:
        for owner, instance in reversed(created):
            applications.destroy_instance(owner, instance)
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
