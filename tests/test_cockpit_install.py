from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "cockpit/integrations/install"


def test_installer_builds_only_runtime_launchers_and_private_assets(tmp_path: Path) -> None:
    real_python = Path(os.environ.get("DIX_PYTHON", DIX / ".venv/bin/python"))
    assert real_python.is_file()
    fake_venv = tmp_path / "venv"
    fake_venv.joinpath("bin").mkdir(parents=True)
    fake_venv.joinpath("bin/python").write_text(f'#!/bin/sh\nexec {real_python} "$@"\n')
    fake_venv.joinpath("bin/python").chmod(0o755)
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        "\n".join(
            (
                f'export DIX_SOURCE_ROOT="{DIX}"',
                f'export DIX_VENV="{fake_venv}"',
                f'export DIX_LAUNCHERS="{launchers}"',
                f'export DIX_BIN="{commands}"',
                "",
            )
        )
    )
    environment = {**os.environ, "DIX_ENV": str(env_file)}
    for _run in range(2):
        result = subprocess.run(
            [str(INSTALL)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    for name in (
        "dix-cockpit",
        "dix-cockpit-owner-shell",
        "dix-cockpit-runtime-status",
    ):
        assert (launchers / f"{name}.py").is_file()
        assert "@DIX_" not in (launchers / f"{name}.toml").read_text()
    for name in (
        "dix-cockpit",
        "dix-cockpit-shell",
        "dix-cockpit-runtime-status",
        "dix-cockpit-clipboard-copy",
        "dix-cockpit-clipboard-paste",
    ):
        assert (commands / name).is_file() and os.access(commands / name, os.X_OK)

    for path in (
        launchers / "cockpit/tmux.conf",
        launchers / "cockpit/zsh/.zshrc",
        launchers / "cockpit/assets/dix.png",
        launchers / "cockpit/assets/roba.png",
    ):
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE((launchers / "cockpit").stat().st_mode) == 0o700

    help_result = subprocess.run(
        [str(commands / "dix-cockpit"), "--help"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert all(
        word in help_result.stdout for word in ("start", "attach", "status", "stop", "reset")
    )
