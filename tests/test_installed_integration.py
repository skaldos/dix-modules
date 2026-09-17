from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALL = ROOT / "sway/integrations/install"


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
    state_root = tmp_path / "state/skaldos/sway"
    env_file.write_text(
        f'export DIX_SOURCE_ROOT="{source}"\n'
        f'export SKALDOS_SWAY_ROOT="{ROOT / "sway"}"\n'
        f'export DIX_VENV="{venv}"\n'
        f'export DIX_LAUNCHERS="{tmp_path / "launchers"}"\n'
        f'export DIX_BIN="{tmp_path / "bin"}"\n'
        f'export SKALDOS_SWAY_STATE_ROOT="{state_root}"\n'
        f'export SKALDOS_SWAY_THEME_DIR="{theme_dir}"\n'
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
