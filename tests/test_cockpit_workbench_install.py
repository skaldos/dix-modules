from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "cockpit/integrations/install-workbench"


def test_optional_installer_materializes_only_local_workbench_surface(tmp_path: Path) -> None:
    real_python = Path(os.environ.get("DIX_PYTHON", DIX / ".venv/bin/python"))
    assert real_python.is_file()
    fake_venv = tmp_path / "venv"
    tools = tmp_path / "tools"
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    fake_venv.joinpath("bin").mkdir(parents=True)
    tools.mkdir()
    fake_venv.joinpath("bin/python").write_text(f'#!/bin/sh\nexec "{real_python}" "$@"\n')
    fake_venv.joinpath("bin/python").chmod(0o755)
    uv_log = tmp_path / "uv.log"
    tools.joinpath("uv").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{uv_log}"\n')
    tools.joinpath("uv").chmod(0o755)
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        f"DIX_VENV={fake_venv}\nDIX_LAUNCHERS={launchers}\nDIX_BIN={commands}\n"
    )
    environment = {
        **os.environ,
        "DIX_ENV": str(env_file),
        "PATH": f"{tools}:{os.environ['PATH']}",
    }

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
            stale = launchers / "cockpit/toml-workbench-modules/cockpit/apps/stale/app.toml"
            stale.parent.mkdir(parents=True)
            stale.write_text("[app]\nid = 'stale'\n")

    projection = launchers / "cockpit/toml-workbench-modules"
    actual = {
        path.relative_to(projection).as_posix()
        for path in projection.rglob("*")
        if path.is_file()
    }
    assert actual == {
        "cockpit/apps/toml_workbench/app.toml",
        "cockpit/apps/toml_workbench/runtime.py",
        "cockpit/compositions/toml_file/composition.toml",
        "cockpit/compositions/toml_file/runtime.py",
        "visidata/compositions/value_workbench/composition.toml",
        "visidata/compositions/value_workbench/runtime.py",
        "visidata/compositions/value_workbench/draft.py",
        "visidata/compositions/value_workbench/ui.py",
        "visidata/compositions/value_workbench/branding.py",
        "visidata/assets/dix.png",
        "visidata/assets/roba.png",
    }
    assert not any(path.is_symlink() for path in projection.rglob("*"))
    assert not (projection / "cockpit/apps/stale").exists()
    assert stat.S_IMODE(projection.stat().st_mode) == 0o700
    launcher_spec = (launchers / "dix-cockpit-toml-workbench.toml").read_text()
    launcher = launchers / "dix-cockpit-toml-workbench.py"
    wrapper = commands / "dix-cockpit-toml-workbench"
    assert launcher.is_file() and os.access(launcher, os.X_OK)
    assert wrapper.is_file() and os.access(wrapper, os.X_OK)
    assert "@SKALDOS_" not in launcher_spec
    assert str(projection / "visidata") in launcher_spec
    assert str(projection / "cockpit") in launcher_spec
    assert all(word not in launcher_spec for word in ("dix/roba", "loom", "control"))
    assert "pip install --python" in uv_log.read_text()

    help_result = subprocess.run(
        [str(wrapper), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "--file" in help_result.stdout and "--logo" in help_result.stdout


def test_privileged_installer_and_launchers_remain_visidata_free() -> None:
    installer = (ROOT / "cockpit/integrations/install").read_text().lower()
    assert "visidata" not in installer
    for name in (
        "dix-cockpit.toml",
        "dix-cockpit-owner-shell.toml",
        "dix-cockpit-runtime-status.toml",
    ):
        assert "visidata" not in (
            ROOT / "cockpit/integrations/launchers" / name
        ).read_text().lower()
