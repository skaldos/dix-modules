from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ClassVar

from visidata import ItemColumn, Sheet, vd


class ControlSheet(Sheet):
    """Show every catalog target; Enter only opens/focuses a stable tmux window."""

    rowtype = "Cockpit daemon"
    columns: ClassVar[list[ItemColumn]] = [
        ItemColumn("catalog_id", width=22),
        ItemColumn("daemon_id", width=22),
        ItemColumn("state", width=10),
        ItemColumn("runtime_root", width=42),
        ItemColumn("logs_root", width=42),
        ItemColumn("connection", width=70),
        ItemColumn("error", width=70),
    ]

    def __init__(
        self,
        *,
        load_rows: Callable[[], Sequence[Mapping[str, object]]],
        open_connection: Callable[[str], object],
        update_status: Callable[[int], object],
        session: str,
        catalog: str,
        socket: str,
        logo: str,
    ) -> None:
        self.load_rows = load_rows
        self.open_connection = open_connection
        self.update_status = update_status
        self.session = session
        self.catalog = catalog
        self.socket = socket
        self.logo = logo
        self.rows: list[dict[str, object]] = []
        super().__init__(self._title(0))

    def _title(self, count: int) -> str:
        return (
            f"{self.logo.upper()} Cockpit | session {self.session} | "
            f"{count} daemons | catalog {self.catalog} | socket {self.socket}"
        )

    def reload(self) -> None:
        values = self.load_rows()
        self.rows = [
            {
                **copy.deepcopy(dict(value)),
                "connection": _preview(value.get("connection")),
                "error": value.get("error") or "",
            }
            for value in values
        ]
        self.name = self._title(len(self.rows))
        self.update_status(len(self.rows))
        vd.status(f"Cockpit catalog reloaded: {len(self.rows)} daemon targets")

    def openRow(self, row: dict[str, Any]) -> None:
        catalog_id = row.get("catalog_id")
        if not isinstance(catalog_id, str) or not catalog_id:
            vd.fail("Cockpit catalog row has no valid catalog_id")
        result = self.open_connection(catalog_id)
        if isinstance(result, Mapping):
            vd.status(
                f"Cockpit connection window {result.get('action', 'opened')}: "
                f"{result.get('window', catalog_id)}"
            )


def _preview(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(value)
