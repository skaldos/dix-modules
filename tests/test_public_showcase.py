from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dix.bootstrap import build_launcher

ROOT = Path(__file__).parents[1].resolve()
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix")).resolve()
NAV = ROOT / "sway/integrations/bin/skaldos-sway-nav"
MANAGE = ROOT / "sway/integrations/bin/skaldos-sway-json"


def _run(command: list[str | Path], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(value) for value in command],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"command failed: {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def _fake_i3ipc(path: Path) -> None:
    path.mkdir()
    (path / "i3ipc.py").write_text(
        """
import os

current = int(os.environ.get("FAKE_SWAY_FOCUSED", "34"))
direction_target = int(os.environ.get("FAKE_SWAY_DIRECTION_TARGET", "32"))

class Node:
    def __init__(self, value, nodes=(), focus=()):
        self.id = value
        self.nodes = list(nodes)
        self.floating_nodes = []
        self.focus = list(focus)

class Tree(Node):
    def __init__(self):
        self.hidden = Node(392)
        self.visible = Node(32)
        self.origin = Node(34)
        self.left = Node(100, [self.visible, self.hidden], [392, 32])
        self.right = Node(200, [self.origin], [34])
        super().__init__(1, [self.left, self.right], [100, 200])

    def find_focused(self):
        return Node(current)

    def leaves(self):
        return [self.visible, self.hidden, self.origin]

class Reply:
    success = True
    error = None

class Connection:
    def get_tree(self):
        return Tree()

    def command(self, value):
        global current
        if "con_id=" in value:
            current = int(value.split("con_id=", 1)[1].split("]", 1)[0])
        elif "focus" in value:
            current = direction_target
        return [Reply()]
""".lstrip()
    )


def test_documented_wrapper_path_runs_real_dix_roba_and_fake_sway() -> None:
    base = Path(tempfile.mkdtemp(prefix="sps-", dir="/tmp"))
    home = base / "home"
    fake = base / "fake"
    state = base / "state"
    home.mkdir()
    state.mkdir()
    _fake_i3ipc(fake)
    launcher = build_launcher(
        DIX / "examples/launchers/dix_roba.toml", base / "dix-roba.py"
    )
    sway_launchers = base / "launchers"
    sway_launchers.mkdir()
    for name in ("skaldos-sway-nav.py", "skaldos-sway-json.py"):
        shutil.copy2(ROOT / "sway/integrations/launchers" / name, sway_launchers / name)
    dix_env = base / "dix.env"
    dix_env.write_text(
        f'export DIX_VENV="{DIX / ".venv"}"\n'
        f'export DIX_LAUNCHERS="{sway_launchers}"\n'
        f'export SKALDOS_SWAY_ROOT="{ROOT / "sway"}"\n'
        f'export DIX_ROBA_RUNTIME_ROOT="{base / "roba-runtime"}"\n'
        f'export DIX_ROBA_LOGS_ROOT="{base / "roba-logs"}"\n'
        f'export SKALDOS_SWAY_GROUP_STATE_FILE="{state / "groups.json"}"\n'
        f'export SKALDOS_SWAY_ACTIVE_MEMBERS_FILE="{state / "active-members"}"\n'
        f'export SKALDOS_SWAY_NAVIGATION_TARGET_FILE="{state / "navigation-target"}"\n'
    )

    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("ROBA_"):
            env.pop(key)
    env.update(
        {
            "HOME": str(home),
            "DIX_ENV": str(dix_env),
            "PYTHONPATH": os.pathsep.join((str(fake), str(DIX / "src"))),
            "DIX_ROBA_RUNTIME_ROOT": str(base / "roba-runtime"),
            "DIX_ROBA_LOGS_ROOT": str(base / "roba-logs"),
            "SKALDOS_SWAY_GROUP_STATE_FILE": str(state / "groups.json"),
            "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE": str(state / "active-members"),
            "SKALDOS_SWAY_NAVIGATION_TARGET_FILE": str(state / "navigation-target"),
            "SKALDOS_SWAY_ROOT": str(ROOT / "sway"),
        }
    )
    python = DIX / ".venv/bin/python"
    daemon = [python, launcher]

    try:
        _run([*daemon, "managed", "start"], env)
        _run(
            [*daemon, "control", "create_context", "--context_id", "skaldos-sway"],
            env,
        )
        assert (
            base
            / "roba-runtime/daemons/default/contexts/dix.control/sockets/skaldos-sway.sock"
        ).is_socket()

        assert json.loads(_run([MANAGE, "create", "work"], env).stdout) is None
        assert _run([MANAGE, "list-lines"], env).stdout == "work\n"

        window_env = {**env, "FAKE_SWAY_FOCUSED": "392"}
        assert json.loads(_run([MANAGE, "add", "work"], window_env).stdout) is True
        assert _run([MANAGE, "memberships-lines"], window_env).stdout == "work\n"
        assert json.loads(_run([MANAGE, "select", "work"], window_env).stdout) is True
        assert json.loads(_run([MANAGE, "current"], window_env).stdout) == "work"

        assert (state / "groups.json").read_text() == (
            '{"groups":{"work":[392]},"active_group":"work"}\n'
        )
        assert (state / "active-members").read_bytes() == b"392\n"
        assert (state / "navigation-target").read_bytes() == b"group\n"

        navigation_env = {
            **env,
            "FAKE_SWAY_FOCUSED": "34",
            "FAKE_SWAY_DIRECTION_TARGET": "32",
        }
        basic = json.loads(_run([NAV, "--target", "basic", "right"], navigation_env).stdout)
        assert basic == {
            "changed": True,
            "direction": "right",
            "focused_id": 32,
            "origin_id": 34,
        }
        group = json.loads(_run([NAV, "--target", "group", "right"], navigation_env).stdout)
        assert group["matched"] is True
        assert group["focused_id"] == 392
        assert group["visited_ids"] == [34, 32, 392]

        assert json.loads(_run([MANAGE, "remove", "work"], window_env).stdout) is True
        assert (state / "active-members").read_bytes() == b"\n"
        assert json.loads(_run([MANAGE, "deactivate"], env).stdout) is True
        assert (state / "navigation-target").read_bytes() == b"basic\n"
    finally:
        subprocess.run(
            [str(value) for value in (*daemon, "daemon", "stop")],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        shutil.rmtree(base, ignore_errors=True)
