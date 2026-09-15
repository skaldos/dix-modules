# ruff: noqa: PLW1510
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dix.bootstrap import build_launcher

DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
ROOT = Path(__file__).parents[1]


def test_clone_shaped_source_assembly_builds_management_launcher(tmp_path, monkeypatch):
    modules = tmp_path / "dix/modules"
    (modules / "dix").mkdir(parents=True)
    for name in ("state", "cli", "roba"):
        (modules / "dix" / name).symlink_to(DIX / "modules/dix" / name, target_is_directory=True)
    shutil.copytree(
        ROOT,
        modules / "skaldos",
        ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__"),
    )
    monkeypatch.setenv("SKALDOS_SWAY_GROUP_STATE_FILE", str(tmp_path / "groups"))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE", str(tmp_path / "members"))
    monkeypatch.setenv("SKALDOS_SWAY_NAVIGATION_TARGET_FILE", str(tmp_path / "target"))
    launcher = build_launcher(
        modules / "skaldos/examples/launchers/skaldos_sway.toml", tmp_path / "skaldos-sway.py"
    )
    result = subprocess.run(
        [sys.executable, str(launcher), "--help"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(DIX / "src")},
    )
    assert result.returncode == 0, result.stderr
    assert "group" in result.stdout
    assert not (modules / "skaldos/sway/apps").joinpath("navigation").exists()
