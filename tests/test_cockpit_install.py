from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "cockpit/integrations/install"


def test_installer_builds_all_launchers_and_preserves_existing_catalog(tmp_path: Path) -> None:
    real_python = Path(os.environ.get("DIX_PYTHON", DIX / ".venv/bin/python"))
    assert real_python.is_file()
    fake_venv = tmp_path / "venv"
    fake_venv.joinpath("bin").mkdir(parents=True)
    fake_venv.joinpath("bin/python").write_text(
        f"#!/bin/sh\nexec {real_python} \"$@\"\n"
    )
    fake_venv.joinpath("bin/python").chmod(0o755)
    tools = tmp_path / "tools"
    tools.mkdir()
    uv_log = tmp_path / "uv.log"
    tools.joinpath("uv").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{uv_log}"\n')
    tools.joinpath("uv").chmod(0o755)
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    catalog = tmp_path / "config/daemons.toml"
    catalog.parent.mkdir()
    catalog.write_text("# user-owned catalog\n")
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        "\n".join(
            (
                f'export DIX_SOURCE_ROOT="{DIX}"',
                f'export DIX_VENV="{fake_venv}"',
                f'export DIX_LAUNCHERS="{launchers}"',
                f'export DIX_BIN="{commands}"',
                f'export DIX_COCKPIT_CATALOG="{catalog}"',
                "",
            )
        )
    )
    environment = {
        **os.environ,
        "DIX_ENV": str(env_file),
        "PATH": f"{tools}:{os.environ['PATH']}",
    }
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
    assert catalog.read_text() == "# user-owned catalog\n"
    assert (launchers / "cockpit/tmux.conf").is_file()
    for name in ("dix-cockpit", "dix-cockpit-control", "dix-cockpit-connection"):
        assert (launchers / f"{name}.py").is_file()
        assert (commands / name).is_file() and os.access(commands / name, os.X_OK)
        assert "@DIX_" not in (launchers / f"{name}.toml").read_text()
    for name in ("dix-cockpit-clipboard-copy", "dix-cockpit-clipboard-paste"):
        assert (commands / name).is_file() and os.access(commands / name, os.X_OK)
    help_result = subprocess.run(
        [str(commands / "dix-cockpit"), "--help"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert all(word in help_result.stdout for word in ("start", "attach", "status", "stop"))
    assert "pip install --python" in uv_log.read_text()
