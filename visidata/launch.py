#!/usr/bin/env python3
"""Start the small VisiData key workbench against an existing ROBA capability socket."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skaldos_workbench.binding import bind_profile
from skaldos_workbench.branding import show_logo
from skaldos_workbench.draft import JsonDraft
from skaldos_workbench.roba_cli import RobaCliAccess

TEMPLATES = Path(__file__).parent / "templates"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locator", required=True, help="existing unix: capability socket")
    parser.add_argument("--key", required=True, help="existing ROBA Context key")
    parser.add_argument("--dix-roba-cli", required=True, type=Path, help="installed CLI executable")
    parser.add_argument("--access-template", type=Path, default=TEMPLATES / "roba-key.toml")
    parser.add_argument("--profile-template", type=Path, default=TEMPLATES / "profile.toml")
    parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
    args = parser.parse_args(argv)

    try:
        access = RobaCliAccess(args.dix_roba_cli, args.locator, args.key)
        profile = bind_profile(args.access_template, args.profile_template, access)
        draft = JsonDraft(profile)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"workbench startup failed: {exc}", file=sys.stderr)
        return 1

    # Import VisiData only once a valid bound value has been loaded.
    try:
        from skaldos_workbench.ui import JsonDraftSheet

        from visidata import vd
    except ImportError:
        print("VisiData is not installed in this Python environment", file=sys.stderr)
        return 1

    show_logo(args.logo)
    vd.options.disp_menu = False
    sheet = JsonDraftSheet(draft, logo=args.logo)
    sheet.reload()
    vd.run(sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
