from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_bilingual_guides_describe_both_navigation_surfaces():
    for relative in ("sway/README.md", "sway/README.de.md"):
        value = (ROOT / relative).read_text()
        for required in (
            "dix-sway-nav",
            "dix-sway-nav-cli",
            "skaldos/sway/core/ipc",
            "skaldos/sway/nav/binding",
            "$$dix_sway_nav",
            "--ids",
            "DIX_SOURCE_ROOT",
            "SKALDOS_SWAY_ROOT",
        ):
            assert required in value


def test_root_readmes_mark_the_branch_as_focused():
    for relative in ("README.md", "README.de.md"):
        value = (ROOT / relative).read_text()
        assert "sway/core" in value and "sway/nav" in value
        assert "Apache-2.0" in value


def test_bilingual_sway_guides_describe_optional_theme_strands():
    for relative in ("sway/README.md", "sway/README.de.md"):
        value = (ROOT / relative).read_text()
        for required in (
            "skaldos/sway/theme/color",
            "skaldos/sway/theme/client_colors",
            "skaldos/sway/theme/client_theme",
            "skaldos/sway/theme/focused_tab_title_colors",
            "skaldos/sway/theme/background",
            "dix/norn/strand",
            "dix/norn/knot",
            "#RRGGBB",
            "dix-sway-theme-cli",
            "theme apply --file",
            "sway/theme/integrations/install",
        ):
            assert required in value

    for relative in ("sway/theme/README.md", "sway/theme/README.de.md"):
        value = (ROOT / relative).read_text()
        assert "skaldos/sway/theme/color" in value
        assert "skaldos/sway/theme/client_colors" in value
        assert "skaldos/sway/theme/client_theme" in value
        assert "skaldos/sway/theme/focused_tab_title_colors" in value
        assert "skaldos/sway/theme/background" in value
        assert "dix/norn/knot" in value
        assert "dix-sway-theme-cli" in value
        assert "theme apply --file" in value
        assert "focused_tab_title" in value and "background" in value
        assert "output *" in value and "solid_color" in value
