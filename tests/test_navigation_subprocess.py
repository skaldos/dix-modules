# ruff: noqa: PLW1510
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def fake(tmp_path):
    path = tmp_path / "fake"
    path.mkdir(exist_ok=True)
    (path / "i3ipc.py").write_text(
        """\ncurrent=34\ncommands=[]\nclass N:\n def __init__(self,id):self.id=id\nclass T:\n def find_focused(self):return N(current)\n def leaves(self):return [N(34),N(32)]\nclass R:success=True;error=None\nclass Connection:\n def get_tree(self):return T()\n def command(self,value):\n  global current\n  commands.append(value)\n  current=32 if "focus" in value else current\n  return [R()]\n"""
    )
    return path


def invoke(tmp_path, target=None, route="basic\n", direction="right"):
    if route is not None:
        (tmp_path / "route").write_text(route)
    (tmp_path / "members").write_text("32\n")
    f = fake(tmp_path)
    cmd = [
        sys.executable,
        str(ROOT / "tests/probes/navigation_probe.py"),
        str(ROOT / "sway"),
        direction,
    ] + ([] if target is None else [target])
    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": str(f),
            "SKALDOS_SWAY_NAVIGATION_TARGET_FILE": str(tmp_path / "route"),
            "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE": str(tmp_path / "members"),
        },
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_basic_closure_excludes_group_and_heavy_modules(tmp_path):
    value = invoke(tmp_path, route=None)
    assert value["code"] == 0 and value["loaded"] == []
    assert json.loads(value["stdout"])["changed"] is True
    assert value["commands"] == ["focus right"]


def test_group_closure_excludes_heavy_modules_and_override_is_not_persisted(tmp_path):
    value = invoke(tmp_path, "group")
    assert value["code"] == 0
    assert value["loaded"] == ["skaldos_sway_active_members", "skaldos_sway_group_navigation"]
    assert (tmp_path / "route").read_text() == "basic\n"


def test_invalid_route_is_runtime_error_without_target_closure(tmp_path):
    value = invoke(tmp_path, route="wat\n")
    assert value["code"] == 1 and value["loaded"] == [] and "runtime error" in value["stderr"]


import pytest


@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
def test_all_directions_share_argparse_surface(tmp_path, direction):
    value = invoke(tmp_path, direction=direction)
    assert value["code"] == 0
    assert value["commands"] == [f"focus {direction}"]


def test_both_overrides_leave_route_byte_identical(tmp_path):
    route = tmp_path / "route"
    invoke(tmp_path, target="basic", route="group\n")
    assert route.read_bytes() == b"group\n"
    invoke(tmp_path, target="group", route="basic\n")
    assert route.read_bytes() == b"basic\n"


def test_argument_error_has_distinct_exit_code(tmp_path):
    fake_path = fake(tmp_path)
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples/launchers/skaldos_sway_navigation.py"), "sideways"],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(fake_path)},
    )
    assert result.returncode == 2
    assert "invalid choice" in result.stderr
