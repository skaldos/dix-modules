from __future__ import annotations

from pathlib import Path

from dix.core.module import inspect_module

ROOT = Path(__file__).parents[1]
SWAY = ROOT / "sway"


def test_sway_is_an_umbrella_with_three_explicit_module_roots():
    assert not (SWAY / "apps").exists()
    assert not (SWAY / "compositions").exists()

    core = inspect_module(SWAY / "core", module_id="skaldos/sway/core")
    nav = inspect_module(SWAY / "nav", module_id="skaldos/sway/nav")
    theme = inspect_module(SWAY / "theme", module_id="skaldos/sway/theme")

    assert core.id == "skaldos/sway/core"
    assert [value.id for value in core.composition_definitions] == [
        "skaldos/sway/core/ipc"
    ]
    assert core.application_definitions == ()

    assert {value.id for value in nav.composition_definitions} == {
        "skaldos/sway/nav/basic_nav",
        "skaldos/sway/nav/binding",
        "skaldos/sway/nav/windows_list_nav",
    }
    assert {value.id for value in nav.application_definitions} == {
        "skaldos/sway/nav/basic",
        "skaldos/sway/nav/cli",
        "skaldos/sway/nav/nav",
        "skaldos/sway/nav/windows_list",
    }

    assert {value.id for value in theme.composition_definitions} == {
        "skaldos/sway/theme/client_colors",
        "skaldos/sway/theme/color",
    }
    assert theme.application_definitions == ()


def test_theme_module_has_no_forbidden_runtime_dependencies():
    product = "\n".join(
        path.read_text()
        for path in (SWAY / "theme").rglob("*")
        if path.is_file() and path.suffix in {".py", ".toml"}
    ).lower()
    for forbidden in ("roba", "pydantic", "typer", "click", "httpx", "i3ipc"):
        assert forbidden not in product
    assert not (SWAY / "theme/apps").exists()
    assert not (SWAY / "theme/integrations").exists()


def test_replacement_branch_has_no_removed_feature_sources():
    forbidden = (
        "groups",
        "themes",
        "themed_groups",
        "active_members",
        "active_theme",
        "navigation_target",
        "theme_files",
        "theme_ipc",
        "themed_group_files",
        "management_entry.py",
        "wofi",
    )
    relative = [path.relative_to(SWAY).as_posix() for path in SWAY.rglob("*")]
    for value in forbidden:
        assert not any(value in path.split("/") for path in relative)
