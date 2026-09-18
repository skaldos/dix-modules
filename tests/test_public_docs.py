from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_bilingual_guides_describe_both_navigation_surfaces():
    for relative in ("sway/README.md", "sway/README.de.md"):
        value = (ROOT / relative).read_text()
        for required in (
            "dix-sway-nav",
            "skaldos-sway-nav",
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
