"""Terminal-only branding with the two user-supplied PNGs."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ASSETS = Path(__file__).parents[1] / "assets"


def logo_path(logo: str) -> Path:
    if logo not in {"dix", "roba"}:
        raise ValueError("logo must be dix or roba")
    return ASSETS / f"{logo}.png"


def logo_command(logo: str) -> list[str]:
    """The exact full-color block rendering selected by the user."""
    return ["chafa", "--fill", "block", "-c", "full", "--scale", "0.5", str(logo_path(logo))]


def show_logo(logo: str, *, pause: bool = True) -> bool:
    """Show a skippable PNG splash; never block data access on small terminals."""
    logo_path(logo)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    size = shutil.get_terminal_size(fallback=(80, 24))
    if size.columns < 70 or size.lines < 22:
        print(f"{logo.upper()} workbench")
        return False
    if shutil.which("chafa") is None:
        print(f"{logo.upper()} workbench (install chafa to view the PNG)")
        return False
    result = subprocess.run(logo_command(logo), check=False)
    if result.returncode:
        print(f"{logo.upper()} workbench (chafa failed)")
        return False
    if pause:
        input("Press Enter for VisiData...")
    return True
