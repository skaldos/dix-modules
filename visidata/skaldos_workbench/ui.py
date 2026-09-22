"""A narrow VisiData view over a detached JSON draft."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from visidata.editor import SuspendCurses

from visidata import ItemColumn, Sheet, vd

from .branding import show_logo
from .draft import JsonDraft, PathPart
from .roba_cli import AccessError


class JsonDraftSheet(Sheet):
    """Drill into a JSON value; only the explicit apply command writes."""

    rowtype = "JSON field"
    columns: ClassVar[list[ItemColumn]] = [
        ItemColumn("key", width=26),
        ItemColumn("type", width=12),
        ItemColumn("preview", width=76),
    ]

    def __init__(
        self, draft: JsonDraft, *, path: tuple[PathPart, ...] = (), logo: str = "dix",
    ) -> None:
        self.draft = draft
        self.path = path
        self.logo = logo
        super().__init__(self._title())

    def _title(self) -> str:
        location = ".".join(map(str, self.path)) or self.draft.profile.field
        dirty = " *draft*" if self.draft.dirty else ""
        return f"{self.logo.upper()} | {self.draft.profile.name}.{location}{dirty}"

    def reload(self) -> None:
        """Redraw only the local draft, never silently re-read the backend."""
        value = self.draft.at(self.path)
        if isinstance(value, dict):
            entries = value.items()
        elif isinstance(value, list):
            entries = enumerate(value)
        else:
            entries = [("value", value)]
        self.rows = [
            {
                "key": str(part),
                "type": _type_name(item),
                "preview": _preview(item),
                "path": self.path + (() if not isinstance(value, (dict, list)) else (part,)),
                "value": item,
            }
            for part, item in entries
        ]
        self.name = self._title()

    def openRow(self, row: dict[str, Any]) -> JsonDraftSheet:
        if not isinstance(row["value"], (dict, list)):
            vd.fail("scalar value: press e to edit JSON")
        child = JsonDraftSheet(self.draft, path=row["path"], logo=self.logo)
        child.reload()
        return child

    def editRow(self, row: dict[str, Any]) -> None:
        if isinstance(row["value"], (dict, list)):
            vd.fail("open object/list with Enter; V0 edits existing scalar leaves")
        before = json.dumps(row["value"], ensure_ascii=False, allow_nan=False)
        raw = vd.input("JSON scalar: ", value=before, record=False)
        try:
            self.draft.replace(row["path"], raw)
        except (ValueError, TypeError, KeyError) as exc:
            vd.fail(str(exc))
        self.reload()
        vd.status("local draft changed; press a to apply whole key")

    def applyDraft(self) -> None:
        try:
            changed = self.draft.apply()
        except (AccessError, ValueError, TypeError, OSError) as exc:
            # Backend errors are already value-free; avoid logging entire payloads.
            vd.fail(f"apply failed ({type(exc).__name__}); local draft retained")
        self.reload()
        vd.status("whole key applied" if changed else "draft unchanged; no write")

    def showBrand(self) -> None:
        with SuspendCurses():
            show_logo(self.logo)


def _type_name(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _preview(value: object) -> str:
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


JsonDraftSheet.addCommand(
    "e", "edit-json-scalar",
    "sheet.editRow(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "edit selected scalar in local JSON draft",
)
JsonDraftSheet.addCommand(
    "a", "apply-whole-key", "sheet.applyDraft()", "apply entire local draft to bound key",
)
JsonDraftSheet.addCommand(
    "B", "show-brand-logo", "sheet.showBrand()", "show selected DIX/ROBA PNG with chafa",
)
