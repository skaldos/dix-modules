from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Bind the generic workbench directly to the declared ROBA Loom."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        workbench: Api,
        loom: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.workbench = workbench
        self.loom = loom

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(
            prog="dix-roba-workbench",
            description="Open an explicit JSON seed in the direct ROBA Loom workbench.",
        )
        parser.add_argument("--seed", required=True, type=Path, help="JSON seed file")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        parser.add_argument(
            "--no-confirm",
            action="store_true",
            help="execute without confirmation (unsafe; intended for local pressure tests)",
        )
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            seed = _read_seed(arguments.seed)
        except (OSError, ValueError) as exc:
            print(f"workbench seed failed: {exc}", file=sys.stderr)
            return 2
        result = self.workbench.require("start")(
            self.loom.require("execute"),
            seed,
            arguments.logo,
            not arguments.no_confirm,
        )
        if type(result) is not int:
            raise TypeError("workbench start must return an integer exit code")
        return result


def _read_seed(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from None


def _reject_constant(_value: str) -> object:
    raise ValueError("seed must contain finite JSON")
