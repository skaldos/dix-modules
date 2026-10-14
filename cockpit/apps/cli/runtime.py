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
    """Expose one explicit privileged Cockpit runtime lifecycle."""

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
        parser = _parser()
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            if arguments.command in {"start", "reset"}:
                result = self._start_or_reset(arguments)
                if not isinstance(result, Mapping):
                    raise TypeError("Cockpit lifecycle operation must return a mapping")
                return 0
            if arguments.command == "attach":
                return int(self.session.require("attach")(session=arguments.session))
            if arguments.command == "status":
                status = self.session.require("status")(session=arguments.session)
                if not isinstance(status, Mapping):
                    raise TypeError("Cockpit status must return a mapping")
                print(json.dumps(status, sort_keys=True, separators=(",", ":")))
                return 0 if status.get("running") is True else 1
            if arguments.command == "stop":
                stopped = self.session.require("stop")(session=arguments.session)
                if not isinstance(stopped, Mapping):
                    raise TypeError("Cockpit stop must return a mapping")
                print(json.dumps(stopped, sort_keys=True, separators=(",", ":")))
                return 0
        except Exception as exc:  # noqa: BLE001 - CLI preserves the concrete local boundary
            print(f"cockpit error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        parser.error("a Cockpit command is required")
        return 2

    def _start_or_reset(self, arguments: argparse.Namespace) -> object:
        shell = _command("dix-cockpit-shell")
        status = _command("dix-cockpit-runtime-status")
        values = {
            "session": arguments.session,
            "logo": arguments.logo,
            "shell_command": [shell, "--session", arguments.session],
            "status_command": [
                status,
                "--session",
                arguments.session,
                "--logo",
                arguments.logo,
                "--daemon-state",
                "running",
            ],
            "attach": True,
        }
        return self.session.require(arguments.command)(**values)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dix-cockpit",
        description="Run one isolated privileged DIX Cockpit runtime.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("start", "create/reuse and attach to one Cockpit runtime"),
        ("reset", "replace one owned Cockpit runtime and attach with a fresh capability"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--session", default="dix")
        command.add_argument("--logo", choices=("dix", "roba"), default="dix")
    for name, help_text in (
        ("attach", "attach only to a healthy existing Cockpit runtime"),
        ("status", "inspect one Cockpit runtime without creating it"),
        ("stop", "stop one provably owned Cockpit runtime"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--session", default="dix")
    return parser


def _command(name: str) -> str:
    binary_root = os.environ.get("DIX_BIN")
    return str(Path(binary_root) / name) if binary_root else name
