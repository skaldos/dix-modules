#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


for relative in (
    "README.md",
    "README.de.md",
    "sway/README.md",
    "sway/README.de.md",
    "sway/theme/README.md",
    "sway/theme/README.de.md",
):
    path = ROOT / relative
    if not path.is_file() or not path.read_text().strip():
        raise SystemExit(f"missing public documentation: {relative}")

for relative in ("sway/README.md", "sway/README.de.md"):
    value = (ROOT / relative).read_text()
    for required in (
        "dix-sway-nav",
        "dix-sway-nav-cli",
        "$$dix_sway_nav",
        "--ids",
        "sway/nav/integrations/install",
        "skaldos/sway/theme/color",
        "skaldos/sway/theme/client_colors",
        "skaldos/sway/theme/client_theme",
        "dix/norn/strand",
        "dix/norn/knot",
        "dix-sway-theme-cli",
        "theme apply --file",
        "sway/theme/integrations/install",
    ):
        if required not in value:
            raise SystemExit(f"{relative} misses {required!r}")

print("public_docs=passed")
