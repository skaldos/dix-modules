# ruff: noqa: PLW1510
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from dix.bootstrap import build_launcher

DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
ROOT = Path(__file__).parents[1]


def run(path, *args, env, cwd):
    value = subprocess.run(
        [sys.executable, str(path), *args], cwd=cwd, env=env, text=True, capture_output=True
    )
    assert value.returncode == 0, f"{args}\n{value.stdout}\n{value.stderr}"
    return value


def test_real_dix_roba_multiprocess_management_path(tmp_path):
    home = Path(tempfile.mkdtemp(prefix="sm-", dir="/tmp"))
    modules = tmp_path / "dix/modules"
    (modules / "dix").mkdir(parents=True)
    for name in ("state", "cli", "roba"):
        (modules / "dix" / name).symlink_to(DIX / "modules/dix" / name, target_is_directory=True)
    shutil.copytree(
        ROOT,
        modules / "skaldos",
        ignore=shutil.ignore_patterns(".git", ".venv", ".pytest_cache", "__pycache__"),
    )
    external = build_launcher(
        modules / "skaldos/examples/launchers/skaldos_sway.toml", tmp_path / "skaldos-sway.py"
    )
    management = modules / "skaldos/examples/launchers/skaldos_sway_management.py"
    roba = build_launcher(DIX / "examples/launchers/dix_roba.toml", tmp_path / "dix-roba.py")
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "i3ipc.py").write_text(
        """\nclass N:\n id=34\nclass T:\n def find_focused(self):return N()\n def leaves(self):return [N()]\nclass R:success=True;error=None\nclass Connection:\n def get_tree(self):return T()\n def command(self,value):return [R()]\n"""
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "PYTHONPATH": os.pathsep.join((str(fake), str(DIX / "src"))),
        "SKALDOS_SWAY_GROUP_STATE_FILE": str(tmp_path / "groups.json"),
        "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE": str(tmp_path / "members"),
        "SKALDOS_SWAY_NAVIGATION_TARGET_FILE": str(tmp_path / "target"),
    }
    try:
        run(roba, "managed", "start", env=env, cwd=tmp_path)
        run(
            roba, "control", "create_context", "--context_id", "skaldos-sway", env=env, cwd=tmp_path
        )
        run(external, "group", "create", "--group", "work", env=env, cwd=tmp_path)
        listed = run(management, "list-lines", env=env, cwd=tmp_path)
        assert listed.stdout == "work\n"
        run(external, "group", "add", "--group", "work", env=env, cwd=tmp_path)
        run(external, "group", "select", "--group", "work", env=env, cwd=tmp_path)
        assert (
            tmp_path / "groups.json"
        ).read_text() == '{"groups":{"work":[34]},"active_group":"work"}\n'
        assert (tmp_path / "members").read_text() == "34\n" and (
            tmp_path / "target"
        ).read_text() == "group\n"
        run(roba, "daemon", "stop", env=env, cwd=tmp_path)
        assert (tmp_path / "groups.json").exists()
        run(roba, "managed", "start", env=env, cwd=tmp_path)
        run(
            roba, "control", "create_context", "--context_id", "skaldos-sway", env=env, cwd=tmp_path
        )
        current = run(external, "group", "current", env=env, cwd=tmp_path)
        assert current.stdout.strip() == "work"
        credentials = ast.literal_eval(
            run(
                roba,
                "control",
                "context_credentials",
                "--context_id",
                "skaldos-sway",
                env=env,
                cwd=tmp_path,
            ).stdout.strip()
        )
        from roba import RobaClient

        assert (
            RobaClient(timeout=5)
            .context(locator=credentials["context_locator"], token=credentials["owner_token"])
            .state()
            == {}
        )
    finally:
        subprocess.run(
            [sys.executable, str(roba), "daemon", "stop"],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
        )
        shutil.rmtree(home, ignore_errors=True)
