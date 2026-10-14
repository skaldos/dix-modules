from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Expose only Cockpit workspace lifecycle; provider lifecycle stays in Loom."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        settings: Api,
        catalog: Api,
        session: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.settings = settings
        self.catalog = catalog
        self.session = session

    def main(self, argv: Sequence[str]) -> int:
        parser = _parser()
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            if arguments.command == "start":
                return self._start(arguments)
            if arguments.command == "attach":
                return self.session.require("attach")(session=arguments.session)
            if arguments.command == "status":
                status = self.session.require("status")(session=arguments.session)
                print(json.dumps(status, sort_keys=True, separators=(",", ":")))
                return 0 if status.get("running") is True else 1
            if arguments.command == "stop":
                stopped = self.session.require("stop")(session=arguments.session)
                print(json.dumps({"session": arguments.session, "stopped": stopped}))
                return 0
        except Exception as exc:  # noqa: BLE001 - CLI preserves the real local boundary
            print(f"cockpit error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        parser.error("a Cockpit command is required")
        return 2

    def _start(self, arguments: argparse.Namespace) -> int:
        catalog_path = self.settings.require("catalog_path")(arguments.catalog)
        entries = self.catalog.require("load")(catalog_path)
        binary_root = os.environ.get("DIX_BIN")
        control = (
            str(Path(binary_root) / "dix-cockpit-control")
            if binary_root
            else "dix-cockpit-control"
        )
        common = [
            "--session",
            arguments.session,
            "--catalog",
            str(catalog_path),
            "--logo",
            arguments.logo,
        ]
        result = self.session.require("start")(
            session=arguments.session,
            catalog=str(catalog_path),
            logo=arguments.logo,
            count=len(entries),
            control_command=[control, "--mode", "body", *common],
            header_command=[control, "--mode", "header", *common],
            attach=True,
        )
        if not isinstance(result, Mapping):
            raise TypeError("Cockpit session start must return a mapping")
        return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dix-cockpit",
        description="Run one isolated DIX Cockpit tmux workspace.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="create/focus and attach to a Cockpit session")
    start.add_argument("--session", default="dix")
    start.add_argument("--catalog")
    start.add_argument("--logo", choices=("dix", "roba"), default="dix")
    for name, help_text in (
        ("attach", "attach only to an existing Cockpit session"),
        ("status", "inspect one Cockpit session without creating it"),
        ("stop", "stop only one Cockpit session"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--session", default="dix")
    return parser
