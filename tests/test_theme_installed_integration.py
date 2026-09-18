from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIX = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
INSTALL = ROOT / "sway/theme/integrations/install"


def _environment(tmp_path: Path) -> tuple[Path, dict[str, str]]:
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
                "# preserved-user-value",
                "",
            )
        )
    )
    return value, {**os.environ, "HOME": str(home), "DIX_ENV": str(value)}


def _run(command: list[str], env: dict[str, str], *, cwd: Path | None = None):
    return subprocess.run(command, text=True, capture_output=True, env=env, cwd=cwd, check=False)


def _fake_i3ipc(tmp_path: Path) -> Path:
    root = tmp_path / "fake"
    root.mkdir()
    (root / "i3ipc.py").write_text(
        '''
import os
from pathlib import Path
class Reply: success=True; error=""
class Connection:
 def command(self,value):
  Path(os.environ["FAKE_SWAY_LOG"]).open("a").write(value+"\\n")
  return [Reply()]
'''.lstrip()
    )
    return root


def test_theme_installer_is_repeatable_and_preserves_the_central_env(tmp_path: Path) -> None:
    env_file, env = _environment(tmp_path)
    original = env_file.read_bytes()

    first = _run([str(INSTALL)], env)
    second = _run([str(INSTALL)], env)
    assert first.returncode == second.returncode == 0, first.stderr + second.stderr
    assert env_file.read_bytes() == original

    binary = tmp_path / "bin/dix-sway-theme-cli"
    assert binary.is_file() and os.access(binary, os.X_OK)
    assert (tmp_path / "launchers/dix-sway-theme-cli.py").is_file()
    spec = (tmp_path / "launchers/dix-sway-theme-cli.toml").read_text()
    assert "@DIX_" not in spec and "@SKALDOS_" not in spec
    for source in (
        DIX / "modules/dix/cli",
        DIX / "modules/dix/norn",
        ROOT / "sway/core",
        ROOT / "sway/theme",
    ):
        assert str(source) in spec
    assert sorted(path.name for path in (tmp_path / "bin").iterdir()) == ["dix-sway-theme-cli"]


def test_installed_theme_cli_applies_from_an_unrelated_working_directory(
    tmp_path: Path,
) -> None:
    _, env = _environment(tmp_path)
    installed = _run([str(INSTALL)], env)
    assert installed.returncode == 0, installed.stderr

    fake = _fake_i3ipc(tmp_path)
    log = tmp_path / "sway.log"
    theme = tmp_path / "theme.toml"
    theme.write_text(
        """
[urgent]
border = "#111111"
background = "#121212"
text = "#131313"
indicator = "#141414"
child_border = "#151515"
""".lstrip()
    )
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    runtime_env = {**env, "PYTHONPATH": str(fake), "FAKE_SWAY_LOG": str(log)}
    result = _run(
        [str(tmp_path / "bin/dix-sway-theme-cli"), "theme", "apply", "--file", str(theme)],
        runtime_env,
        cwd=unrelated,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert log.read_text() == "client.urgent #111111 #121212 #131313 #141414 #151515\n"
