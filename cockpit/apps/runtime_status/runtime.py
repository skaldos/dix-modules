from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from dix.core.application import ApplicationRuntimeContext


class Runtime:
    """Render only caller-provided non-secret branding and runtime status."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-runtime-status")
        parser.add_argument("--session", default="dix")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        parser.add_argument("--daemon-state", default="running")
        parser.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
        try:
            arguments = parser.parse_args(list(argv))
            self._render(arguments.logo, arguments.session, arguments.daemon_state)
            if arguments.once:
                return 0
            while True:
                time.sleep(3600)
        except SystemExit as exc:
            return int(exc.code)
        except Exception as exc:  # noqa: BLE001 - pane must retain a visible local error
            print(f"cockpit runtime status error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    @staticmethod
    def _render(logo: str, session: str, daemon_state: str) -> None:
        asset_root = Path(
            os.environ.get("DIX_COCKPIT_ASSET_ROOT", str(Path(__file__).parents[2] / "assets"))
        )
        image = asset_root / f"{logo}.png"
        rendered = False
        if image.is_file() and shutil.which("chafa") is not None:
            rendered = (
                subprocess.run(
                    [
                        "chafa",
                        "-c",
                        "full",
                        "--color-extractor",
                        "median",
                        "--symbols",
                        "block",
                        "--dither-grain",
                        "8x8",
                        "--dither-intensity",
                        "5.0",
                        "--scale",
                        "0.6",
                        str(image),
                    ],
                    check=False,
                ).returncode
                == 0
            )
        if not rendered:
            print(f"{logo.upper()} Cockpit", flush=True)
        print(f"session: {session}\nROBA: {daemon_state}", flush=True)
