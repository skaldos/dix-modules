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
    environment = {
        **os.environ,
        "DIX_ENV": str(env_file),
        "SKALDOS_VISIDATA_ROOT": str(tmp_path / "deliberately-absent-visidata"),
    }
    runtime_module = launchers / "cockpit/runtime-module"
    for run in range(2):
        result = subprocess.run(
            [str(INSTALL)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        if run == 0:
            stale = runtime_module / "apps/stale/app.toml"
            stale.parent.mkdir(parents=True)
            stale.write_text("[app]\nid = 'stale'\n")

    assert {path.name for path in (runtime_module / "apps").iterdir()} == {
        "cli",
        "owner_shell",
        "runtime_status",
    }
    assert {path.name for path in (runtime_module / "compositions").iterdir()} == {
        "config",
        "roba_runtime",
        "tmux_workspace",
        "cockpit_session",
    }
    assert {path.name for path in (runtime_module / "assets").iterdir()} == {
        "dix.png",
        "roba.png",
    }
    assert {path.relative_to(runtime_module).as_posix() for path in runtime_module.rglob("*") if path.is_file()} == {
        "apps/cli/app.toml",
        "apps/cli/runtime.py",
        "apps/owner_shell/app.toml",
        "apps/owner_shell/runtime.py",
        "apps/runtime_status/app.toml",
        "apps/runtime_status/runtime.py",
        "compositions/config/composition.toml",
        "compositions/config/runtime.py",
        "compositions/roba_runtime/composition.toml",
        "compositions/roba_runtime/runtime.py",
        "compositions/tmux_workspace/composition.toml",
        "compositions/tmux_workspace/runtime.py",
        "compositions/cockpit_session/composition.toml",
        "compositions/cockpit_session/runtime.py",
        "assets/dix.png",
        "assets/roba.png",
        "integrations/tmux/cockpit.conf",
        "integrations/zsh/.zshrc",
    }
    assert not any(path.is_symlink() for path in runtime_module.rglob("*"))
    assert not (runtime_module / "apps/stale").exists()

    for name in (
        "dix-cockpit",
        "dix-cockpit-owner-shell",
        "dix-cockpit-runtime-status",
    ):
        assert (launchers / f"{name}.py").is_file()
        assert "@DIX_" not in (launchers / f"{name}.toml").read_text()
        assert str(runtime_module) in (launchers / f"{name}.toml").read_text()
        assert "visidata" not in (launchers / f"{name}.toml").read_text().lower()
        assert "visidata" not in (launchers / f"{name}.py").read_text().lower()
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

    status_result = subprocess.run(
        [str(commands / "dix-cockpit"), "status", "--session", "not-running"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert status_result.returncode == 1, status_result.stderr
    assert '"running":false' in status_result.stdout

    for name in ("dix-cockpit-owner-shell", "dix-cockpit-runtime-status"):
        internal_help = subprocess.run(
            [str(fake_venv / "bin/python"), str(launchers / f"{name}.py"), "--help"],
            env=environment,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert internal_help.returncode == 0, internal_help.stderr
