from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "cockpit/integrations/install-ui"


def test_optional_ui_installer_materializes_only_master_surface(tmp_path: Path) -> None:
    real_python = Path(os.environ.get("DIX_PYTHON", DIX / ".venv/bin/python"))
    assert real_python.is_file()
    fake_venv = tmp_path / "venv"
    tools = tmp_path / "tools"
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    fake_venv.joinpath("bin").mkdir(parents=True)
    tools.mkdir()
    commands.mkdir()
    fake_venv.joinpath("bin/python").write_text(
        f'#!/bin/sh\nexec "{real_python}" "$@"\n'
    )
    fake_venv.joinpath("bin/python").chmod(0o755)
    uv_log = tmp_path / "uv.log"
    tools.joinpath("uv").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{uv_log}"\n')
    tools.joinpath("uv").chmod(0o755)
    for name in ("dix-cockpit", "dix-cockpit-shell", "dix-cockpit-runtime-status"):
        path = commands / name
        path.write_text("#!/bin/sh\nexit 0\n")
        path.chmod(0o755)
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        "\n".join(
            (
                f'DIX_SOURCE_ROOT="{DIX}"',
                f'DIX_VENV="{fake_venv}"',
                f'DIX_LAUNCHERS="{launchers}"',
                f'DIX_BIN="{commands}"',
                "",
            )
        )
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
            stale = launchers / "cockpit/master-ui-modules/cockpit/apps/stale/app.toml"
            stale.parent.mkdir(parents=True)
            stale.write_text("[app]\nid = 'stale'\n")

    projection = launchers / "cockpit/master-ui-modules"
    actual = {
        path.relative_to(projection).as_posix()
        for path in projection.rglob("*")
        if path.is_file()
    }
    assert actual == {
        "cockpit/apps/store_workbench/app.toml",
        "cockpit/apps/store_workbench/runtime.py",
        "cockpit/compositions/store_workbench/composition.toml",
        "cockpit/compositions/store_workbench/runtime.py",
        "cockpit/compositions/store_workbench/session.py",
        "cockpit/compositions/store_workbench/ui.py",
        "cockpit/apps/store_browser/app.toml",
        "cockpit/apps/store_browser/runtime.py",
        "cockpit/compositions/store_catalog/composition.toml",
        "cockpit/compositions/store_catalog/runtime.py",
        "cockpit/compositions/store_providers/composition.toml",
        "cockpit/compositions/store_providers/runtime.py",
        "cockpit/compositions/roba_store/composition.toml",
        "cockpit/compositions/roba_store/runtime.py",
        "cockpit/compositions/store_browser/composition.toml",
        "cockpit/compositions/store_browser/runtime.py",
        "cockpit/compositions/store_browser/session.py",
        "cockpit/compositions/store_browser/ui.py",
        "cockpit/apps/ui/app.toml",
        "cockpit/apps/ui/runtime.py",
        "cockpit/apps/master_workbench/app.toml",
        "cockpit/apps/master_workbench/runtime.py",
        "cockpit/compositions/config/composition.toml",
        "cockpit/compositions/config/runtime.py",
        "cockpit/compositions/roba_runtime/composition.toml",
        "cockpit/compositions/roba_runtime/runtime.py",
        "cockpit/compositions/tmux_workspace/composition.toml",
        "cockpit/compositions/tmux_workspace/runtime.py",
        "cockpit/compositions/cockpit_session/composition.toml",
        "cockpit/compositions/cockpit_session/runtime.py",
        "visidata/compositions/loom_workbench/composition.toml",
        "visidata/compositions/loom_workbench/runtime.py",
        "visidata/compositions/loom_workbench/session.py",
        "visidata/compositions/loom_workbench/ui.py",
        "visidata/compositions/loom_workbench/branding.py",
        "visidata/compositions/value_workbench/composition.toml",
        "visidata/compositions/value_workbench/runtime.py",
        "visidata/compositions/value_workbench/draft.py",
        "visidata/compositions/value_workbench/ui.py",
        "visidata/compositions/value_workbench/branding.py",
        "visidata/assets/dix.png",
        "visidata/assets/roba.png",
    }
    assert stat.S_IMODE(projection.stat().st_mode) == 0o700
    assert not any(path.is_symlink() for path in projection.rglob("*"))
    assert not (projection / "cockpit/apps/stale").exists()
    assert not any(
        (projection / "cockpit/apps" / name).exists()
        for name in (
            "daemon_catalog",
            "roba_connections",
            "control_window",
            "connection_window",
            "toml_workbench",
        )
    )

    for name in ("dix-cockpit-ui", "dix-cockpit-master-workbench", "dix-cockpit-store-browser",
                 "dix-cockpit-store-workbench"):
        launcher_spec = (launchers / f"{name}.toml").read_text()
        launcher = launchers / f"{name}.py"
        wrapper = commands / name
        assert launcher.is_file() and os.access(launcher, os.X_OK)
        assert wrapper.is_file() and os.access(wrapper, os.X_OK)
        assert "@DIX_" not in launcher_spec and "@SKALDOS_" not in launcher_spec
        assert str(projection / "visidata") in launcher_spec
        assert str(projection / "cockpit") in launcher_spec
        help_result = subprocess.run(
            [str(wrapper), "--help"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert help_result.returncode == 0, help_result.stderr
    assert "start" in subprocess.run(
        [str(commands / "dix-cockpit-ui"), "--help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    assert "pip install --python" in uv_log.read_text()


def test_ui_install_requires_the_separate_base_runtime(tmp_path: Path) -> None:
    fake_venv = tmp_path / "venv"
    fake_venv.joinpath("bin").mkdir(parents=True)
    fake_venv.joinpath("bin/python").write_text("#!/bin/sh\nexit 0\n")
    fake_venv.joinpath("bin/python").chmod(0o755)
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        f"DIX_SOURCE_ROOT={DIX}\nDIX_VENV={fake_venv}\n"
        f"DIX_LAUNCHERS={tmp_path / 'launchers'}\nDIX_BIN={tmp_path / 'bin'}\n"
    )
    result = subprocess.run(
        [str(INSTALL)],
        cwd=ROOT,
        env={**os.environ, "DIX_ENV": str(env_file)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Install the Cockpit runtime first" in result.stderr


def test_ui_docs_and_source_keep_optional_boundary_explicit() -> None:
    installer = INSTALL.read_text()
    runtime_installer = (ROOT / "cockpit/integrations/install").read_text().lower()
    assert "visidata" not in runtime_installer
    assert "master-ui-modules" in installer
    assert "daemon_catalog" not in installer
    assert "roba_connections" not in installer
    for text in (
        (ROOT / "cockpit/README.md").read_text(),
        (ROOT / "cockpit/README.de.md").read_text(),
    ):
        assert "./cockpit/integrations/install-ui" in text
        assert "dix-cockpit-ui start --session dix --logo dix" in text
        assert "Enter" in text and "Space" in text
        assert "Control" in text and "token" in text.lower()
        assert "C-a" in text and "copy" in text.lower()
