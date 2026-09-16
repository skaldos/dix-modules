from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
INTEGRATIONS = ROOT / "sway" / "integrations"
BIN = INTEGRATIONS / "bin"
LAUNCHERS = INTEGRATIONS / "launchers"


def _layout(tmp_path: Path) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    dix_home = home / ".dix"
    dix_root = dix_home / "src" / "dix"
    module_root = dix_root / "modules" / "skaldos" / "sway"
    launcher_root = dix_home / "share" / "dix" / "launchers"
    user_bin = home / ".local" / "bin"
    python = dix_root / ".venv" / "bin" / "python"

    launcher_root.mkdir(parents=True)
    user_bin.mkdir(parents=True)
    module_root.mkdir(parents=True)
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "arg=%s\\n" "$@"\nexit "${FAKE_EXIT:-0}"\n')
    python.chmod(0o755)

    for name in ("skaldos-sway-nav.py", "skaldos-sway-json.py"):
        shutil.copy2(LAUNCHERS / name, launcher_root / name)
    for name in ("skaldos-sway-nav", "skaldos-sway-json"):
        shutil.copy2(BIN / name, user_bin / name)
        (user_bin / name).chmod(0o755)

    (dix_home / "env").write_text(
        f'export DIX_VENV="{dix_root / ".venv"}"\n'
        f'export DIX_LAUNCHERS="{launcher_root}"\n'
        f'export SKALDOS_SWAY_ROOT="{module_root}"\n'
    )
    return home, user_bin, launcher_root


def _run(home: Path, path: Path, *arguments: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(path), *arguments],
        env={**os.environ, "HOME": str(home), **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )


def test_sway_owns_one_exact_dependency() -> None:
    assert (ROOT / "sway" / "requirements.txt").read_text() == "i3ipc==2.2.1\n"
    assert "i3ipc" not in (Path(os.environ["DIX_REPOSITORY"]) / "pyproject.toml").read_text()


def test_wrappers_load_one_central_environment_and_forward_arguments(tmp_path: Path) -> None:
    home, user_bin, launcher_root = _layout(tmp_path)

    nav = _run(home, user_bin / "skaldos-sway-nav", "--target", "group", "left")
    assert nav.returncode == 0, nav.stderr
    assert nav.stdout.splitlines() == [
        f"arg={launcher_root / 'skaldos-sway-nav.py'}",
        "arg=--target",
        "arg=group",
        "arg=left",
    ]

    management = _run(
        home,
        user_bin / "skaldos-sway-json",
        "select",
        "work",
        env={"FAKE_EXIT": "23"},
    )
    assert management.returncode == 23
    assert management.stdout.splitlines() == [
        f"arg={launcher_root / 'skaldos-sway-json.py'}",
        "arg=select",
        "arg=work",
    ]


def test_explicit_environment_file_replaces_default_home_location(tmp_path: Path) -> None:
    home, user_bin, launcher_root = _layout(tmp_path)
    explicit = tmp_path / "custom" / "dix.env"
    explicit.parent.mkdir()
    explicit.write_text((home / ".dix" / "env").read_text())
    (home / ".dix" / "env").unlink()

    result = _run(
        home,
        user_bin / "skaldos-sway-json",
        "list-lines",
        env={"DIX_ENV": str(explicit)},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"arg={launcher_root / 'skaldos-sway-json.py'}",
        "arg=list-lines",
    ]


def test_wrapper_reports_missing_central_environment(tmp_path: Path) -> None:
    home, user_bin, _ = _layout(tmp_path)
    (home / ".dix" / "env").unlink()

    result = _run(home, user_bin / "skaldos-sway-nav", "left")

    assert result.returncode == 1
    assert "DIX environment file is not readable" in result.stderr


def test_wrapper_reports_missing_dix_environment(tmp_path: Path) -> None:
    home, user_bin, _ = _layout(tmp_path)
    (home / ".dix" / "src" / "dix" / ".venv" / "bin" / "python").unlink()

    result = _run(home, user_bin / "skaldos-sway-nav", "left")

    assert result.returncode == 1
    assert "DIX environment Python is not executable" in result.stderr


def test_sway_fragment_only_addresses_installed_commands() -> None:
    config = (INTEGRATIONS / "sway" / "config").read_text()
    for value in (
        "$skaldos_bin/skaldos-sway-nav",
        "$skaldos_bin/skaldos-sway-wofi-select",
        "$skaldos_bin/skaldos-sway-wofi-add",
        "$skaldos_bin/skaldos-sway-wofi-remove",
    ):
        assert value in config
    for value in (
        "DIX_ROBA_RUNTIME_ROOT",
        "SKALDOS_SWAY_GROUP_STATE_FILE",
        "SKALDOS_SWAY_MANAGEMENT",
        "exec_always",
    ):
        assert value not in config
    assert not any(line.startswith("mode ") for line in config.splitlines())


def test_environment_template_is_posix_and_exports_all_shared_boundaries(tmp_path: Path) -> None:
    home = tmp_path / "home"
    runtime = tmp_path / "runtime"
    state = tmp_path / "state"
    home.mkdir()
    runtime.mkdir()
    command = (
        '. "$1"; printf "%s\\n" "$DIX_ROBA_RUNTIME_ROOT" "$DIX_ROBA_LOGS_ROOT" '
        '"$SKALDOS_SWAY_GROUP_STATE_FILE" "$DIX_LAUNCHERS"'
    )
    result = subprocess.run(
        [
            "/bin/sh",
            "-c",
            command,
            "_",
            str(INTEGRATIONS / "env"),
        ],
        env={"HOME": str(home), "XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(state)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        str(runtime / "dix" / "roba"),
        str(state / "dix" / "roba" / "logs"),
        str(state / "skaldos" / "sway" / "groups.json"),
        str(home / ".local" / "share" / "dix" / "launchers"),
    ]
