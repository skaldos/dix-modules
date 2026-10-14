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
    """Resolve non-secret catalog identity locally before exposing the Loom capability."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        catalog: Api,
        connections: Api,
        workbench: Api,
        loom: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.catalog = catalog
        self.connections = connections
        self.workbench = workbench
        self.loom = loom

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-connection")
        parser.add_argument("--catalog", required=True, type=Path)
        parser.add_argument("--catalog-id", required=True)
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        parser.add_argument("--no-confirm", action="store_true", help=argparse.SUPPRESS)
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            entries = self.catalog.require("load")(arguments.catalog)
            selected = [entry for entry in entries if entry.get("catalog_id") == arguments.catalog_id]
            if len(selected) != 1:
                raise ValueError(f"catalog target does not exist: {arguments.catalog_id}")
            resolved = self.connections.require("resolve")(selected[0])
            if not isinstance(resolved, Mapping):
                raise TypeError("Cockpit connection resolver must return a mapping")
            if resolved.get("state") == "error":
                raise RuntimeError(str(resolved.get("error") or "unknown connection error"))
            seed = resolved.get("connection")
            if not isinstance(seed, dict):
                raise TypeError("Cockpit connection resolver returned no Loom seed")
            result = self.workbench.require("start")(
                self.loom.require("execute"),
                seed,
                arguments.logo,
                not arguments.no_confirm,
            )
            if type(result) is not int:
                raise TypeError("Loom workbench start must return an integer")
            return result
        except Exception as exc:  # noqa: BLE001 - show the exact selected target failure
            print(f"cockpit connection error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
