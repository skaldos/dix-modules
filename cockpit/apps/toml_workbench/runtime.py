from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Load one explicit TOML source once and start the local value workbench."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        file: Api,
        workbench: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.file = file
        self.workbench = workbench

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(
            prog="dix-cockpit-toml-workbench",
            description="Edit one explicit TOML file as a disposable local value draft.",
        )
        parser.add_argument("--file", required=True, type=Path, help="read-only TOML source")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            value = self.file.require("load")(arguments.file)
            result = self.workbench.require("start")(
                value,
                arguments.logo,
                str(arguments.file),
            )
            if type(result) is not int:
                raise TypeError("local value workbench must return an integer exit code")
            return result
        except Exception as exc:  # noqa: BLE001 - CLI keeps the exact local file/UI boundary visible
            print(f"TOML workbench error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
