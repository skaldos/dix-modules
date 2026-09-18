from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_focused_source_tree_contains_explicit_core_navigation_and_theme_modules():
    sway = ROOT / "sway"
    assert sorted(
        path.name
        for path in sway.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    ) == ["core", "nav", "theme"]
    assert not (sway / "apps").exists()
    assert not (sway / "compositions").exists()

    tracked_text = "\n".join(
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    for removed in (
        "sway/apps/groups",
        "sway/apps/themes",
        "sway/apps/themed_groups",
        "sway/integrations/wofi",
        "sway/management_entry.py",
    ):
        assert removed not in tracked_text


def test_navigation_delivery_files_have_inspectable_ownership():
    integration = ROOT / "sway/nav/integrations"
    executables = (
        integration / "install",
        integration / "bin/dix-sway-nav",
        integration / "bin/dix-sway-nav-cli",
        integration / "launchers/dix-sway-nav.py",
    )
    for path in executables:
        assert path.is_file() and os.access(path, os.X_OK)

    template = (integration / "launchers/dix-sway-nav-cli.toml").read_text()
    assert 'application = "skaldos/sway/nav/cli"' in template
    assert 'id = "dix/cli"' in template
    assert 'id = "skaldos/sway/core"' in template
    assert 'id = "skaldos/sway/nav"' in template


def test_theme_source_delivery_is_composition_only():
    theme = ROOT / "sway/theme"
    assert {
        path.relative_to(theme).as_posix()
        for path in theme.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    } == {
        "README.de.md",
        "README.md",
        "compositions/client_colors/client_colors.toml",
        "compositions/client_colors/composition.toml",
        "compositions/client_colors/runtime.py",
        "compositions/client_colors/strand.toml",
        "compositions/color/composition.toml",
        "compositions/color/runtime.py",
        "compositions/color/strand.toml",
    }
