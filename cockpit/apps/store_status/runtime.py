from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from dix.core.application import ApplicationRuntimeContext


class Runtime:
    """Intentional owner-visible output, never a credential-bearing launch argument or log."""

    def __init__(self, *, context: ApplicationRuntimeContext, config: Mapping[str, object], catalog):
        self.catalog = catalog

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-store-status")
        parser.add_argument("--session", default="dix")
        parser.add_argument("--store-id", required=True)
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        parser.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
        try:
            args = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            record = self.catalog.require("record")(args.store_id, args.session)
            self._logo(args.logo)
            print("Privileged Store status · owner view", flush=True)
            print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
            if args.once:
                return 0
            while True:
                time.sleep(3600)
        except Exception as exc:  # noqa: BLE001 - do not echo catalog values in failure logs
            print(f"Cockpit Store status failed: {type(exc).__name__}", file=sys.stderr)
            return 2

    @staticmethod
    def _logo(logo):
        root = Path(os.environ.get("DIX_COCKPIT_ASSET_ROOT", str(Path(__file__).parents[2]/"assets")))
        image = root / f"{logo}.png"
        if image.is_file() and shutil.which("chafa"):
            result = subprocess.run(["chafa", "-c", "full", "--color-extractor", "median",
                "--symbols", "block", "--dither-grain", "8x8", "--dither-intensity", "5.0",
                "--scale", "0.6", str(image)], check=False)
            if result.returncode == 0:
                return
        print(f"{logo.upper()} Cockpit", flush=True)
