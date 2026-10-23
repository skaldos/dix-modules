from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Expose only the convenient start path for the optional master workspace."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        session: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.session = session

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-ui")
        commands = parser.add_subparsers(dest="command", required=True)
        start = commands.add_parser("start", help="start or focus the master workspace")
        start.add_argument("--session", default="dix")
        start.add_argument("--logo", choices=("dix", "roba"), default="dix")
        stores = commands.add_parser("stores", help="open or focus two read-only Store browsers")
        stores.add_argument("--session", default="dix")
        stores.add_argument("--logo", choices=("dix", "roba"), default="dix")
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)

        try:
            binary_root = Path(os.environ["DIX_BIN"])
            if arguments.command == "stores":
                self.session.require("open_stores")(
                    session=arguments.session,
                    commands={side: [str(binary_root / "dix-cockpit-store-browser"),
                                     "--session", arguments.session, "--logo", arguments.logo,
                                     "--side", side] for side in ("A", "B")})
                if not os.environ.get("TMUX"):
                    self.session.require("attach")(session=arguments.session)
                return 0
            self.session.require("start_master")(
                session=arguments.session,
                logo=arguments.logo,
                shell_command=[
                    str(binary_root / "dix-cockpit-shell"),
                    "--session",
                    arguments.session,
                ],
                status_command=[
                    str(binary_root / "dix-cockpit-runtime-status"),
                    "--session",
                    arguments.session,
                    "--logo",
                    arguments.logo,
                    "--daemon-state",
                    "running",
                ],
                workbench_command=[
                    str(binary_root / "dix-cockpit-master-workbench"),
                    "--session",
                    arguments.session,
                    "--logo",
                    arguments.logo,
                ],
                attach=True,
            )
            return 0
        except Exception as exc:  # noqa: BLE001 - visible optional UI boundary
            print(f"cockpit UI error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
