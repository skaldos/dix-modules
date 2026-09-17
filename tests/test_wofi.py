# ruff: noqa: PLW1510
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

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
    result, log = run("select", tmp_path, "[No active group]")
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
    chooser.write_text("#!/bin/sh\ncat >/dev/null\nprintf '[+ New group]\\n'\n")
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
    result, log = run("select", tmp_path, "  No active group")
    assert result.returncode == 0 and log.endswith("select No active group\n")

    result, log = run("add", tmp_path, "  + New group")
    assert result.returncode == 0 and log.endswith("add + New group\n")

    result, log = run("remove", tmp_path, "  No active group")
    assert result.returncode == 0 and log.endswith("remove No active group\n")


def test_unframed_choice_fails_without_mutation(tmp_path):
    result, log = run("select", tmp_path, "work")
    assert result.returncode == 1
    assert log == "list-lines\n"
    assert "invalid Wofi selection" in result.stderr


def _theme_tools(tmp_path, *, themes="dix\nroba\n", choice="dix", menu_exit=0):
    log = tmp_path / "theme-log"
    manage = tmp_path / "theme-manage"
    menu = tmp_path / "theme-menu"
    manage.write_text(
        f'''#!/bin/sh
printf '%s\n' "$*" >> {log}
if [ "$*" = "theme list_lines" ]; then printf '{themes}'; fi
'''
    )
    menu.write_text(
        f'''#!/bin/sh
cat >/dev/null
printf '%s\n' '{choice}'
exit {menu_exit}
'''
    )
    manage.chmod(0o755)
    menu.chmod(0o755)
    return log, manage, menu


def test_theme_chooser_applies_catalog_selection(tmp_path):
    log, manage, menu = _theme_tools(tmp_path, choice="roba")
    result = subprocess.run(
        [str(ROOT / "theme")],
        env={
            **os.environ,
            "SKALDOS_SWAY_THEME_MANAGEMENT": str(manage),
            "SKALDOS_SWAY_WOFI": str(menu),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text() == "theme list_lines\ntheme apply --theme roba\n"


def test_theme_chooser_rejects_value_outside_catalog(tmp_path):
    log, manage, menu = _theme_tools(tmp_path, choice="unknown")
    result = subprocess.run(
        [str(ROOT / "theme")],
        env={
            **os.environ,
            "SKALDOS_SWAY_THEME_MANAGEMENT": str(manage),
            "SKALDOS_SWAY_WOFI": str(menu),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert log.read_text() == "theme list_lines\n"
    assert "invalid Wofi selection" in result.stderr


@pytest.mark.parametrize(("themes", "menu_exit"), (("", 0), ("dix\n", 1)))
def test_theme_chooser_empty_catalog_or_cancel_is_clean(tmp_path, themes, menu_exit):
    log, manage, menu = _theme_tools(tmp_path, themes=themes, menu_exit=menu_exit)
    result = subprocess.run(
        [str(ROOT / "theme")],
        env={
            **os.environ,
            "SKALDOS_SWAY_THEME_MANAGEMENT": str(manage),
            "SKALDOS_SWAY_WOFI": str(menu),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text() == "theme list_lines\n"


def test_default_theme_wofi_commits_initial_entry(tmp_path):
    log, manage, _menu = _theme_tools(tmp_path)
    arguments = tmp_path / "theme-arguments"
    wofi = tmp_path / "wofi"
    wofi.write_text(
        f'''#!/bin/sh
printf '%s\n' "$@" > {arguments}
sed -n '1p'
'''
    )
    wofi.chmod(0o755)
    result = subprocess.run(
        [str(ROOT / "theme")],
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "SKALDOS_SWAY_THEME_MANAGEMENT": str(manage),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text() == "theme list_lines\ntheme apply --theme dix\n"
    assert arguments.read_text().splitlines() == [
        "--dmenu",
        "--no-custom-entry",
        "--prompt",
        "Sway theme",
    ]


@pytest.mark.parametrize(
    ("adapter", "prompt", "expected_command"),
    (
        ("select", "Sway group", "select work\n"),
        ("add", "Add window to group", "add work\n"),
        ("remove", "Remove window from group", "remove work\n"),
    ),
)
def test_default_wofi_commits_initial_existing_entry(
    tmp_path, adapter, prompt, expected_command
):
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
        [str(ROOT / adapter)],
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
    query = "memberships-lines\n" if adapter == "remove" else "list-lines\n"
    assert log.read_text() == query + expected_command
    assert arguments.read_text().splitlines() == [
        "--dmenu",
        "--no-custom-entry",
        "--prompt",
        prompt,
    ]
    action_rows = {
        "select": "[No active group]\n[+ New group]\n",
        "add": "[+ New group]\n",
        "remove": "",
    }
    assert entries.read_text() == action_rows[adapter] + "  work\n  private\n"


def test_shipped_wofi_ui_is_english():
    scripts = {name: (ROOT / name).read_text() for name in ("select", "add", "remove", "theme")}
    combined = "\n".join(scripts.values())

    for value in ("Keine Gruppe", "Neue Gruppe", "Zu Gruppe", "Aus Gruppe"):
        assert value not in combined

    assert "[No active group]" in scripts["select"]
    assert "[+ New group]" in scripts["select"]
    assert "[+ New group]" in scripts["add"]
    assert "--prompt 'Sway group'" in scripts["select"]
    assert "--prompt 'New group name'" in scripts["select"]
    assert "--prompt 'New group name'" in scripts["add"]
    assert "--prompt 'Add window to group'" in scripts["add"]
    assert "--prompt 'Remove window from group'" in scripts["remove"]
    assert "--prompt 'Sway theme'" in scripts["theme"]
