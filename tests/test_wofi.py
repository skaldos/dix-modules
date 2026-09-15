# ruff: noqa: PLW1510
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1] / "sway/integrations/wofi"


def tools(tmp_path):
    log = tmp_path / "log"
    log.unlink(missing_ok=True)
    manage = tmp_path / "manage"
    menu = tmp_path / "menu"
    manage.write_text(
        f"""#!/bin/sh\necho "$*" >> {log}\ncase "$1" in list-lines) printf 'work\\nprivate\\n';; memberships-lines) printf 'work\\nprivate\\n';; esac\n"""
    )
    menu.write_text("#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' \"$CHOICE\"\n")
    manage.chmod(0o755)
    menu.chmod(0o755)
    return log, manage, menu


def run(name, tmp_path, choice, name_choice=""):
    log, manage, menu = tools(tmp_path)
    env = {
        **os.environ,
        "SKALDOS_SWAY_MANAGEMENT": str(manage),
        "SKALDOS_SWAY_WOFI": str(menu),
        "SKALDOS_SWAY_WOFI_NAME": str(menu),
        "CHOICE": choice,
    }
    result = subprocess.run([str(ROOT / name)], env=env, text=True, capture_output=True)
    return result, log.read_text() if log.exists() else ""


def test_select_existing_and_none(tmp_path):
    result, log = run("select", tmp_path, "  work")
    assert result.returncode == 0 and log.endswith("select work\n")
    result, log = run("select", tmp_path, "[Keine Gruppe]")
    assert result.returncode == 0 and log.endswith("deactivate\n")


def test_add_does_not_select_and_remove_uses_memberships(tmp_path):
    result, log = run("add", tmp_path, "  private")
    assert result.returncode == 0 and log == "list-lines\nadd private\n" and "select" not in log
    result, log = run("remove", tmp_path, "  work")
    assert result.returncode == 0 and log == "memberships-lines\nremove work\n"


def test_cancel_is_clean(tmp_path):
    log, manage, menu = tools(tmp_path)
    menu.write_text("#!/bin/sh\ncat >/dev/null\nexit 1\n")
    menu.chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "select")],
        env={**os.environ, "SKALDOS_SWAY_MANAGEMENT": str(manage), "SKALDOS_SWAY_WOFI": str(menu)},
    )
    assert result.returncode == 0 and log.read_text() == "list-lines\n"


def test_select_new_group_uses_explicit_management_calls(tmp_path):
    log, manage, _menu = tools(tmp_path)
    name = tmp_path / "name"
    name.write_text("#!/bin/sh\ncat >/dev/null\nprintf 'fresh\\n'\n")
    name.chmod(0o755)
    chooser = tmp_path / "chooser"
    chooser.write_text("#!/bin/sh\ncat >/dev/null\nprintf '[+ Neue Gruppe]\\n'\n")
    chooser.chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "select")],
        env={
            **os.environ,
            "SKALDOS_SWAY_MANAGEMENT": str(manage),
            "SKALDOS_SWAY_WOFI": str(chooser),
            "SKALDOS_SWAY_WOFI_NAME": str(name),
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0 and log.read_text() == "list-lines\ncreate fresh\nselect fresh\n"


def test_action_like_group_names_remain_real_groups(tmp_path):
    result, log = run("select", tmp_path, "  Keine Gruppe")
    assert result.returncode == 0 and log.endswith("select Keine Gruppe\n")

    result, log = run("add", tmp_path, "  + Neue Gruppe")
    assert result.returncode == 0 and log.endswith("add + Neue Gruppe\n")

    result, log = run("remove", tmp_path, "  Keine Gruppe")
    assert result.returncode == 0 and log.endswith("remove Keine Gruppe\n")


def test_unframed_choice_fails_without_mutation(tmp_path):
    result, log = run("select", tmp_path, "work")
    assert result.returncode == 1
    assert log == "list-lines\n"
    assert "invalid Wofi selection" in result.stderr


def test_default_wofi_commits_initial_existing_entry(tmp_path):
    log, manage, _menu = tools(tmp_path)
    arguments = tmp_path / "arguments"
    entries = tmp_path / "entries"
    wofi = tmp_path / "wofi"
    wofi.write_text(
        f"""#!/bin/sh
printf '%s\\n' "$@" > {arguments}
cat > {entries}
sed -n '/^  /{{p;q;}}' {entries}
"""
    )
    wofi.chmod(0o755)

    result = subprocess.run(
        [str(ROOT / "remove")],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "SKALDOS_SWAY_MANAGEMENT": str(manage),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text() == "memberships-lines\nremove work\n"
    assert arguments.read_text().splitlines() == [
        "--dmenu",
        "--no-custom-entry",
        "--prompt",
        "Aus Gruppe",
    ]
    assert entries.read_text() == "  work\n  private\n"
