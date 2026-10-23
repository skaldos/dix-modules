from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from dix.core.application import ApplicationRuntimeContext


class Runtime:
    def __init__(self, *, context: ApplicationRuntimeContext, config: Mapping[str, object],
                 workbench):
        self.workbench = workbench

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-store-workbench")
        parser.add_argument("--session", default="dix")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        try:
            args = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            return self.workbench.require("start")(args.session, args.logo)
        except Exception as exc:  # noqa: BLE001 - do not expose credential-bearing startup errors
            print(f"Store workbench failed: {type(exc).__name__}", file=sys.stderr)
            return 2
