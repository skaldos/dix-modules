from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Own the Cockpit catalog sheet and non-secret tmux window bridge."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        catalog: Api,
        connections: Api,
        session: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.catalog = catalog
        self.connections = connections
        self.session = session

    def main(self, argv: Sequence[str]) -> int:
        parser = _parser()
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)
        try:
            if arguments.mode == "header":
                return self._header(arguments.logo, arguments.session, arguments.once)
            return self._body(arguments)
        except Exception as exc:  # noqa: BLE001 - the window must display the actual local error
            print(f"cockpit control error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    def _body(self, arguments: argparse.Namespace) -> int:
        from visidata import vd

        from .ui import ControlSheet

        catalog_path = Path(arguments.catalog).expanduser().resolve(strict=False)
        paths = self.session.require("paths")(catalog=str(catalog_path))

        def rows() -> list[dict[str, object]]:
            entries = self.catalog.require("load")(catalog_path)
            result = self.connections.require("resolve_all")(entries)
            if not isinstance(result, list):
                raise TypeError("Cockpit connection resolver must return a list")
            return result

        def open_connection(catalog_id: str) -> object:
            binary_root = os.environ.get("DIX_BIN")
            command = (
                str(Path(binary_root) / "dix-cockpit-connection")
                if binary_root
                else "dix-cockpit-connection"
            )
            return self.session.require("open_connection")(
                session=arguments.session,
                catalog_id=catalog_id,
                command=[
                    command,
                    "--catalog",
                    str(catalog_path),
                    "--catalog-id",
                    catalog_id,
                    "--logo",
                    arguments.logo,
                ],
            )

        def update_status(count: int) -> object:
            return self.session.require("update_status")(
                session=arguments.session,
                catalog=str(catalog_path),
                count=count,
                logo=arguments.logo,
            )

        vd.options.disp_menu = False
        sheet = ControlSheet(
            load_rows=rows,
            open_connection=open_connection,
            update_status=update_status,
            session=arguments.session,
            catalog=str(catalog_path),
            socket=str(paths["socket"]),
            logo=arguments.logo,
        )
        sheet.reload()
        vd.run(sheet)
        return 0

    @staticmethod
    def _header(logo: str, session: str, once: bool) -> int:
        asset_root = Path(
            os.environ.get(
                "DIX_COCKPIT_ASSET_ROOT",
                str(Path(__file__).parents[3] / "visidata" / "assets"),
            )
        )
        image = asset_root / f"{logo}.png"
        rendered = False
        if image.is_file() and shutil.which("chafa") is not None:
            rendered = subprocess.run(
                ["chafa", "--fill", "block", "-c", "full", "--scale", "0.5", str(image)],
                check=False,
            ).returncode == 0
        if not rendered:
            print(f"{logo.upper()} Cockpit | session {session}", flush=True)
        if once:
            return 0
        while True:
            time.sleep(3600)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dix-cockpit-control")
    parser.add_argument("--mode", choices=("body", "header"), default="body")
    parser.add_argument("--session", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
    parser.add_argument("--once", action="store_true", help=argparse.SUPPRESS)
    return parser
