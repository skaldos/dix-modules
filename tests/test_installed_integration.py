from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALL = ROOT / "sway/integrations/install"
NAVIGATION = ROOT / "sway/integrations/navigation"
NAVIGATION_INSTALL = NAVIGATION / "install"


def test_installer_copies_example_themes_once_and_preserves_user_bytes(tmp_path):
    home = tmp_path / "home"
    venv = tmp_path / "venv"
    python = venv / "bin/python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)
    source = tmp_path / "dix"
    (source / "examples/launchers").mkdir(parents=True)
    env_file = tmp_path / "dix.env"
    theme_dir = tmp_path / "config/skaldos/sway/themes"
    themed_group_dir = tmp_path / "config/skaldos/sway/themed-groups"
    state_root = tmp_path / "state/skaldos/sway"
    env_file.write_text(
        f'export DIX_SOURCE_ROOT="{source}"\n'
        f'export SKALDOS_SWAY_ROOT="{ROOT / "sway"}"\n'
        f'export DIX_VENV="{venv}"\n'
        f'export DIX_LAUNCHERS="{tmp_path / "launchers"}"\n'
        f'export DIX_BIN="{tmp_path / "bin"}"\n'
        f'export SKALDOS_SWAY_STATE_ROOT="{state_root}"\n'
        f'export SKALDOS_SWAY_THEME_DIR="{theme_dir}"\n'
        f'export SKALDOS_SWAY_THEMED_GROUP_DIR="{themed_group_dir}"\n'
    )
    environment = {**os.environ, "HOME": str(home), "DIX_ENV": str(env_file)}

    first = subprocess.run(
        [str(INSTALL)], env=environment, text=True, capture_output=True, check=False
    )
    assert first.returncode == 0, first.stderr
    assert (theme_dir / "dix.toml").read_bytes() == (
        ROOT / "sway/integrations/themes/dix.toml"
    ).read_bytes()
    assert (theme_dir / "roba.toml").read_bytes() == (
        ROOT / "sway/integrations/themes/roba.toml"
    ).read_bytes()
    assert themed_group_dir.is_dir()
    assert (theme_dir / "wallpapers/dix.png").read_bytes() == (
        ROOT / "sway/integrations/themes/wallpapers/dix.png"
    ).read_bytes()
    assert (theme_dir / "wallpapers/roba.png").read_bytes() == (
        ROOT / "sway/integrations/themes/wallpapers/roba.png"
    ).read_bytes()
    theme_chooser = tmp_path / "bin/skaldos-sway-wofi-theme"
    assert theme_chooser.is_file()
    assert 'SKALDOS_SWAY_THEME_MANAGEMENT="$DIX_BIN/skaldos-sway"' in theme_chooser.read_text()

    custom_theme = b"# user-owned\n"
    custom_wallpaper = b"user-owned wallpaper\n"
    (theme_dir / "dix.toml").write_bytes(custom_theme)
    (theme_dir / "wallpapers/dix.png").write_bytes(custom_wallpaper)
    second = subprocess.run(
        [str(INSTALL)], env=environment, text=True, capture_output=True, check=False
    )
    assert second.returncode == 0, second.stderr
    assert (theme_dir / "dix.toml").read_bytes() == custom_theme
    assert (theme_dir / "wallpapers/dix.png").read_bytes() == custom_wallpaper


def test_navigation_installer_owns_only_current_nav_delivery_and_removes_legacy(tmp_path):
    home = tmp_path / "home"
    venv = tmp_path / "venv"
    python = venv / "bin/python"
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    python.parent.mkdir(parents=True)
    launchers.mkdir()
    commands.mkdir()
    python.write_text("#!/bin/sh\nexit 0\n")
    python.chmod(0o755)

    legacy_launcher = launchers / "skaldos-sway-nav.py"
    legacy_command = commands / "skaldos-sway-nav"
    unrelated_launcher = launchers / "keep.py"
    unrelated_command = commands / "keep"
    for path in (legacy_launcher, legacy_command, unrelated_launcher, unrelated_command):
        path.write_text(f"keep-or-remove:{path.name}\n")

    env_file = tmp_path / "dix.env"
    env_file.write_text(
        f'export DIX_VENV="{venv}"\n'
        f'export DIX_LAUNCHERS="{launchers}"\n'
        f'export DIX_BIN="{commands}"\n'
        f'export SKALDOS_SWAY_ROOT="{ROOT / "sway"}"\n'
    )
    environment = {**os.environ, "HOME": str(home), "DIX_ENV": str(env_file)}

    first = subprocess.run(
        [str(NAVIGATION_INSTALL)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stderr

    installed_launcher = launchers / "dix-sway-nav.py"
    installed_command = commands / "dix-sway-nav"
    assert installed_launcher.read_bytes() == (
        NAVIGATION / "launchers/dix-sway-nav.py"
    ).read_bytes()
    assert installed_command.read_bytes() == (
        NAVIGATION / "bin/dix-sway-nav"
    ).read_bytes()
    assert installed_launcher.stat().st_mode & 0o111
    assert installed_command.stat().st_mode & 0o111
    assert not legacy_launcher.exists()
    assert not legacy_command.exists()
    assert unrelated_launcher.read_text() == "keep-or-remove:keep.py\n"
    assert unrelated_command.read_text() == "keep-or-remove:keep\n"
    assert not (launchers / "skaldos-sway.py").exists()
    assert not (commands / "skaldos-sway").exists()
    assert not (commands / "dix-roba").exists()

    installed_launcher.write_text("stale launcher\n")
    installed_command.write_text("stale command\n")
    second = subprocess.run(
        [str(NAVIGATION_INSTALL)],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert second.returncode == 0, second.stderr
    assert installed_launcher.read_bytes() == (
        NAVIGATION / "launchers/dix-sway-nav.py"
    ).read_bytes()
    assert installed_command.read_bytes() == (
        NAVIGATION / "bin/dix-sway-nav"
    ).read_bytes()
