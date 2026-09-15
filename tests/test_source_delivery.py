from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
BIN = ROOT / "sway" / "integrations" / "bin"


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    dix_root = tmp_path / "workspace" / "dix"
    module_root = dix_root / "modules" / "skaldos" / "sway"
    wrapper_root = module_root / "integrations" / "bin"
    wrapper_root.mkdir(parents=True)
    for name in ("skaldos-sway-nav", "skaldos-sway-json"):
        shutil.copy2(BIN / name, wrapper_root / name)
        (wrapper_root / name).chmod(0o755)
    (module_root / "navigation_entry.py").write_text("# navigation fixture\n")
    (module_root / "management_entry.py").write_text("# management fixture\n")
    python = dix_root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "arg=%s\\n" "$@"\nexit "${FAKE_EXIT:-0}"\n')
    python.chmod(0o755)
    return dix_root, module_root


def _run(path: Path, *arguments: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [str(path), *arguments],
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )


def test_sway_owns_one_exact_dependency() -> None:
    assert (ROOT / "sway" / "requirements.txt").read_text() == "i3ipc==2.2.1\n"
    assert "i3ipc" not in (Path(os.environ["DIX_REPOSITORY"]) / "pyproject.toml").read_text()


def test_wrappers_derive_clone_layout_and_forward_arguments(tmp_path: Path) -> None:
    dix_root, module_root = _layout(tmp_path)

    nav = _run(
        module_root / "integrations" / "bin" / "skaldos-sway-nav",
        "--target",
        "group",
        "left",
    )
    assert nav.returncode == 0, nav.stderr
    assert nav.stdout.splitlines() == [
        f"arg={module_root / 'navigation_entry.py'}",
        "arg=--target",
        "arg=group",
        "arg=left",
    ]

    management = _run(
        module_root / "integrations" / "bin" / "skaldos-sway-json",
        "select",
        "work",
        env={"FAKE_EXIT": "23"},
    )
    assert management.returncode == 23
    assert management.stdout.splitlines() == [
        f"arg={module_root / 'management_entry.py'}",
        "arg=select",
        "arg=work",
    ]
    assert dix_root.is_dir()


def test_symlink_and_explicit_roots_use_the_same_delivery(tmp_path: Path) -> None:
    dix_root, module_root = _layout(tmp_path)
    user_bin = tmp_path / "home" / ".local" / "bin"
    user_bin.mkdir(parents=True)
    link = user_bin / "skaldos-sway-nav"
    link.symlink_to(module_root / "integrations" / "bin" / "skaldos-sway-nav")

    linked = _run(link, "right")
    assert linked.returncode == 0, linked.stderr
    assert linked.stdout.splitlines() == [
        f"arg={module_root / 'navigation_entry.py'}",
        "arg=right",
    ]

    explicit = _run(
        BIN / "skaldos-sway-json",
        "list-lines",
        env={"SKALDOS_DIX_ROOT": str(dix_root), "SKALDOS_SWAY_ROOT": str(module_root)},
    )
    assert explicit.returncode == 0, explicit.stderr
    assert explicit.stdout.splitlines() == [
        f"arg={module_root / 'management_entry.py'}",
        "arg=list-lines",
    ]


def test_wrapper_reports_missing_dix_environment(tmp_path: Path) -> None:
    dix_root, module_root = _layout(tmp_path)
    (dix_root / ".venv" / "bin" / "python").unlink()

    result = _run(module_root / "integrations" / "bin" / "skaldos-sway-nav", "left")

    assert result.returncode == 1
    assert "DIX environment Python is not executable" in result.stderr


def test_sway_fragment_uses_delivered_commands_and_explicit_state() -> None:
    config = (ROOT / "sway" / "integrations" / "sway" / "config").read_text()
    for value in (
        "skaldos-sway-nav",
        "skaldos-sway-json",
        "SKALDOS_SWAY_GROUP_STATE_FILE",
        "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE",
        "SKALDOS_SWAY_NAVIGATION_TARGET_FILE",
        "integrations/wofi/select",
        "integrations/wofi/add",
        "integrations/wofi/remove",
    ):
        assert value in config
    assert not any(line.startswith("mode ") for line in config.splitlines())
