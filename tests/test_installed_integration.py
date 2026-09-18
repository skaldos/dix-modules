from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "sway/nav/integrations/install"


def environment(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    home = tmp_path / "home"
    home.mkdir()
    launchers = tmp_path / "launchers"
    binaries = tmp_path / "bin"
    value = tmp_path / "dix.env"
    value.write_text(
        "\n".join(
            (
                f'export DIX_SOURCE_ROOT="{DIX}"',
                f'export DIX_VENV="{DIX / ".venv"}"',
                f'export DIX_LAUNCHERS="{launchers}"',
                f'export DIX_BIN="{binaries}"',
                f'export SKALDOS_SWAY_ROOT="{ROOT / "sway"}"',
                "",
            )
        )
    )
    return value, {**os.environ, "HOME": str(home), "DIX_ENV": str(value)}


def fake_i3ipc(tmp_path: Path) -> Path:
    root = tmp_path / "fake"
    root.mkdir()
    (root / "i3ipc.py").write_text(
        '''
import os
from pathlib import Path
current=34
class Node:
 def __init__(self,value):self.id=value
class Tree:
 def find_focused(self):return Node(current)
 def leaves(self):return [Node(34),Node(23),Node(42)]
class Reply:success=True;error=None
class Connection:
 def get_tree(self):return Tree()
 def command(self,value):
  global current
  log=os.environ.get("FAKE_SWAY_LOG")
  if log: Path(log).open("a").write(value+"\\n")
  if value.startswith("focus "):current=23
  return [Reply()]
'''.lstrip()
    )
    return root


def run(
    command: list[str], env: dict[str, str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def test_installer_delivers_both_commands_and_is_repeatable(tmp_path):
    env_file, env = environment(tmp_path)
    launchers = tmp_path / "launchers"
    binaries = tmp_path / "bin"
    launchers.mkdir()
    binaries.mkdir()
    for stale in (
        launchers / "skaldos-sway-nav.py",
        launchers / "skaldos-sway-nav.toml",
        binaries / "skaldos-sway-nav",
    ):
        stale.write_text("stale")

    first = run([str(INSTALL)], env)
    second = run([str(INSTALL)], env)
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr

    for name in ("dix-sway-nav", "dix-sway-nav-cli"):
        assert (binaries / name).is_file()
        assert os.access(binaries / name, os.X_OK)
        assert (launchers / f"{name}.py").is_file()
    assert not (binaries / "skaldos-sway-nav").exists()
    assert not (launchers / "skaldos-sway-nav.py").exists()
    assert not (launchers / "skaldos-sway-nav.toml").exists()

    spec = (launchers / "dix-sway-nav-cli.toml").read_text()
    assert "@DIX_CLI_MODULE@" not in spec
    assert str(DIX / "modules/dix/cli") in spec
    assert str(ROOT / "sway/core") in spec
    assert str(ROOT / "sway/nav") in spec

    help_result = run([str(binaries / "dix-sway-nav-cli"), "--help"], env)
    assert help_result.returncode == 0, help_result.stderr
    assert "basic" in help_result.stdout and "windows-list" in help_result.stdout
    assert env_file.is_file()


def test_installed_commands_execute_against_fake_sway(tmp_path):
    _, env = environment(tmp_path)
    installed = run([str(INSTALL)], env)
    assert installed.returncode == 0, installed.stderr

    fake = fake_i3ipc(tmp_path)
    log = tmp_path / "sway.log"
    runtime_env = {
        **env,
        "PYTHONPATH": str(fake),
        "FAKE_SWAY_LOG": str(log),
    }
    binaries = tmp_path / "bin"
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()

    direct = run(
        [str(binaries / "dix-sway-nav"), "right", "basic"],
        runtime_env,
        cwd=unrelated_cwd,
    )
    assert direct.returncode == 0, direct.stderr
    assert '"executed":"basic"' in direct.stdout

    managed = run(
        [
            str(binaries / "dix-sway-nav-cli"),
            "windows-list",
            "set",
            "--ids",
            "23",
            "--ids",
            "42",
        ],
        runtime_env,
        cwd=unrelated_cwd,
    )
    assert managed.returncode == 0, managed.stderr
    assert log.read_text().splitlines() == [
        "focus right",
        "set $dix_sway_nav windows-list 23 42",
    ]
