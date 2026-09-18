# ruff: noqa: PLW1510
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def fake(tmp_path):
    path = tmp_path / "fake"
    path.mkdir(exist_ok=True)
    (path / "i3ipc.py").write_text(
        '''
import os
current=int(os.environ.get("FAKE_SWAY_CURRENT", "34"))
commands=[]
failures=int(os.environ.get("FAKE_SWAY_FAILURES", "0"))
class N:
 def __init__(self,id,nodes=(),focus=()):
  self.id=id;self.nodes=list(nodes);self.floating_nodes=[];self.focus=list(focus)
class T(N):
 def __init__(self):
  self.hidden=N(392);self.visible=N(32);self.origin=N(34)
  if os.environ.get("FAKE_SWAY_FLAT") == "1":
   super().__init__(1,[self.visible,self.hidden,self.origin],[34,32,392]);return
  self.left=N(100,[self.visible,self.hidden],[392,32])
  self.right=N(200,[self.origin],[34])
  super().__init__(1,[self.left,self.right],[100,200])
 def find_focused(self):return N(current)
 def leaves(self):return [self.visible,self.hidden,self.origin]
class R:success=True;error=None
class Connection:
 def get_tree(self):return T()
 def command(self,value):
  global current,failures
  commands.append(value)
  if failures:
   failures-=1
   raise RuntimeError("synthetic Sway failure")
  if "con_id=" in value: current=int(value.split("con_id=",1)[1].split("]",1)[0])
  elif "focus" in value:
   current=34 if os.environ.get("FAKE_SWAY_TOGGLE") == "1" and current==32 else 32
  return [R()]
'''
    )
    return path


def invoke(tmp_path, *arguments, failures=0, root=None, extra_env=None):
    fake_path = fake(tmp_path)
    old_route = tmp_path / "must-not-read-route"
    old_members = tmp_path / "must-not-read-members"
    command = [
        sys.executable,
        str(ROOT / "tests/probes/navigation_probe.py"),
        str(root or ROOT / "sway"),
        *arguments,
    ]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": str(fake_path),
            "FAKE_SWAY_FAILURES": str(failures),
            "SKALDOS_SWAY_NAVIGATION_TARGET_FILE": str(old_route),
            "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE": str(old_members),
            **(extra_env or {}),
        },
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert not old_route.exists() and not old_members.exists()
    return value


def envelope(value):
    return json.loads(value["stdout"])


@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
def test_basic_strategy_is_stateless_and_framework_free(tmp_path, direction):
    value = invoke(tmp_path, direction, "basic")
    assert value["code"] == 0 and value["loaded"] == [] and value["stderr"] == ""
    assert envelope(value) == {
        "executed": "basic",
        "fallback": False,
        "requested": "basic",
        "result": {
            "changed": True,
            "direction": direction,
            "focused_id": 32,
            "origin_id": 34,
        },
    }
    assert value["commands"] == [f"focus {direction}"]


def test_windows_list_strategy_and_empty_noop(tmp_path):
    value = invoke(tmp_path, "right", "windows-list", "392")
    result = envelope(value)
    assert result["requested"] == result["executed"] == "windows-list"
    assert result["fallback"] is False
    assert result["result"]["focused_id"] == 392
    assert value["commands"] == ["focus right", "[con_id=392] focus"]

    empty = invoke(tmp_path, "up", "windows-list")
    assert envelope(empty)["result"]["visited_ids"] == [34]
    assert empty["commands"] == [] and envelope(empty)["fallback"] is False


@pytest.mark.parametrize(
    "arguments,requested",
    [
        (("left",), "missing"),
        (("left", "unknown"), "unknown"),
        (("left", "basic", "9"), "basic"),
        (("left", "windows-list", "x"), "windows-list"),
        (("left", "windows-list", "1", "1"), "windows-list"),
    ],
)
def test_route_and_parameter_errors_fallback_once(tmp_path, arguments, requested):
    value = invoke(tmp_path, *arguments)
    result = envelope(value)
    assert value["code"] == 0 and "primary error:" in value["stderr"]
    assert result["requested"] == requested
    assert result["executed"] == "basic" and result["fallback"] is True
    assert value["commands"] == ["focus left"]


def test_windows_list_build_failure_falls_back(tmp_path):
    root = tmp_path / "sway"
    (root / "compositions/ipc").mkdir(parents=True)
    (root / "compositions/basic_nav").mkdir(parents=True)
    (root / "apps/nav").mkdir(parents=True)
    (root / "navigation_entry.py").write_bytes(
        (ROOT / "sway/navigation_entry.py").read_bytes()
    )
    for path in (
        "compositions/ipc/runtime.py",
        "compositions/basic_nav/runtime.py",
        "apps/nav/runtime.py",
    ):
        source = ROOT / "sway" / path
        (root / path).write_bytes(source.read_bytes())
    value = invoke(tmp_path, "right", "windows-list", "32", root=root)
    assert value["code"] == 0 and envelope(value)["fallback"] is True
    assert "windows_list_nav/runtime.py" in value["stderr"]
    assert value["commands"] == ["focus right"]


def test_window_loop_error_falls_back_from_current_focus(tmp_path):
    value = invoke(tmp_path, "right", "windows-list", "392", failures=1)
    assert value["code"] == 0 and envelope(value)["fallback"] is True
    assert value["commands"] == ["focus right", "focus right"]


def test_windows_list_regular_no_match_restores_origin(tmp_path):
    value = invoke(
        tmp_path,
        "right",
        "windows-list",
        "392",
        extra_env={"FAKE_SWAY_FLAT": "1", "FAKE_SWAY_TOGGLE": "1"},
    )
    result = envelope(value)["result"]
    assert result["matched"] is False and result["restored"] is True
    assert result["focused_id"] == 34 and result["visited_ids"] == [34, 32]
    assert value["commands"] == ["focus right", "focus right", "[con_id=34] focus"]


def test_double_failure_has_no_success_json(tmp_path):
    value = invoke(tmp_path, "right", "windows-list", "392", failures=2)
    assert value["code"] == 1 and value["stdout"] == ""
    assert "primary error:" in value["stderr"] and "fallback error:" in value["stderr"]
    assert value["commands"] == ["focus right", "focus right"]


@pytest.mark.parametrize("arguments", [(), ("sideways",), ("sideways", "basic")])
def test_missing_or_invalid_direction_is_hard_failure(tmp_path, arguments):
    value = invoke(tmp_path, *arguments)
    assert value["code"] == 2 and value["stdout"] == ""
    assert "argument error:" in value["stderr"] and value["commands"] == []
