from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from dix.core.application import ApplicationRuntimeContext


class Runtime:
    def __init__(self, *, context: ApplicationRuntimeContext, config: Mapping[str, object],
                 browser) -> None:
        self.browser = browser

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-store-browser")
        parser.add_argument("--session", default="dix")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        parser.add_argument("--side", choices=("A", "B"), default="A")
        try:
            args = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            return self.browser.require("start")(args.session, args.logo, args.side)
        except Exception as exc:  # noqa: BLE001 - do not print unknown credential-bearing values
            print(f"Cockpit Store browser failed: {type(exc).__name__}", file=sys.stderr)
            return 2
