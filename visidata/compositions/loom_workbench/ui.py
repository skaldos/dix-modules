from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from visidata.editor import SuspendCurses

from visidata import ItemColumn, Sheet, vd

from .branding import show_logo
from .session import LoomDraft, LoomSession, ObjectReference

type DraftPath = tuple[str | int, ...]
SHIFT_ENTER_KEY = "Alt+[13;2u"


class ReferenceSheet(Sheet):
    """One row per complete reference; Enter only creates a local draft."""

    rowtype = "Loom reference"
    columns: ClassVar[list[ItemColumn]] = [
        ItemColumn("object_id", width=24),
        ItemColumn("description", width=48),
        ItemColumn("value", width=76),
    ]

    def __init__(
        self,
        session: LoomSession,
        *,
        references: Sequence[ObjectReference] | None = None,
        logo: str = "dix",
        confirm_execute: bool = True,
    ) -> None:
        self.session = session
        self.references = (
            session.reference_snapshot()
            if references is None
            else tuple(
                ObjectReference(
                    reference.object_id,
                    reference.description,
                    copy.deepcopy(reference.value),
                )
                for reference in references
            )
        )
        self.logo = logo
        self.confirm_execute = confirm_execute
        super().__init__(self._title())

    def _title(self) -> str:
        return (
            f"{self.logo.upper()} Loom | {len(self.references)} references | "
            f"history {len(self.session.history)}"
        )

    def reload(self) -> None:
        self.rows = [
            {
                "object_id": reference.object_id,
                "description": reference.description,
                "value": _preview(reference.value),
                "reference": reference,
            }
            for reference in self.references
        ]
        self.name = self._title()
        if not self.rows:
            vd.status("Loom returned an empty reference set")

    def openRow(self, row: dict[str, Any]) -> DraftSheet:
        draft = self.session.inspect_reference(row["reference"])
        sheet = DraftSheet(
            self.session,
            draft,
            logo=self.logo,
            confirm_execute=self.confirm_execute,
        )
        sheet.reload()
        return sheet

    def executeRow(self, row: dict[str, Any]) -> None:
        draft = self.session.inspect_reference(row["reference"])
        _confirm_and_execute(
            self.session,
            draft,
            self.logo,
            confirm_execute=self.confirm_execute,
        )

    def showBrand(self) -> None:
        with SuspendCurses():
            show_logo(self.logo)


class DraftSheet(Sheet):
    """Recursively inspect and locally edit one detached reference value."""

    rowtype = "Loom draft field"
    columns: ClassVar[list[ItemColumn]] = [
        ItemColumn("key", width=26),
        ItemColumn("type", width=16),
        ItemColumn("value", width=76),
    ]

    def __init__(
        self,
        session: LoomSession,
        draft: LoomDraft,
        *,
        path: DraftPath = (),
        logo: str = "dix",
        confirm_execute: bool = True,
    ) -> None:
        self.session = session
        self.draft = draft
        self.path = path
        self.logo = logo
        self.confirm_execute = confirm_execute
        super().__init__(self._title())

    def _title(self) -> str:
        location = ".".join(map(str, self.path)) or "value"
        dirty = " *draft*" if self.draft.dirty else ""
        return f"{self.logo.upper()} | {self.draft.reference.object_id}.{location}{dirty}"

    def reload(self) -> None:
        value = self.draft.at(self.path)
        if isinstance(value, Mapping):
            entries = value.items()
        elif isinstance(value, list):
            entries = enumerate(value)
        else:
            entries = [("value", value)]
        nested = isinstance(value, (Mapping, list))
        self.rows = [
            {
                "key": str(part),
                "type": _type_name(item),
                "value": _preview(item),
                "native": item,
                "path": self.path + ((part,) if nested else ()),
            }
            for part, item in entries
        ]
        self.name = self._title()

    def openRow(self, row: dict[str, Any]) -> DraftSheet:
        value = row["native"]
        if not isinstance(value, (Mapping, list)):
            vd.fail("scalar/native value: use e or r for a JSON-compatible replacement")
        sheet = DraftSheet(
            self.session,
            self.draft,
            path=row["path"],
            logo=self.logo,
            confirm_execute=self.confirm_execute,
        )
        sheet.reload()
        return sheet

    def editScalar(self, row: dict[str, Any]) -> None:
        if isinstance(row["native"], (Mapping, list)):
            vd.fail("container selected: use r to replace the complete JSON subtree")
        self._edit(row)

    def replaceSubtree(self, row: dict[str, Any]) -> None:
        self._edit(row)

    def _edit(self, row: dict[str, Any]) -> None:
        current = row["native"]
        if not _is_json_value(current):
            vd.fail("selected native value is not losslessly JSON-editable")
            return
        initial = json.dumps(current, ensure_ascii=False, allow_nan=False)
        raw = vd.input("JSON replacement: ", value=initial, record=False)
        try:
            self.draft.replace_json(row["path"], raw)
        except (ValueError, TypeError, KeyError) as exc:
            vd.fail(str(exc))
        self.reload()
        vd.status("local draft changed; use Shift+Enter for explicit Loom execution")

    def executeDraft(self) -> None:
        _confirm_and_execute(
            self.session,
            self.draft,
            self.logo,
            confirm_execute=self.confirm_execute,
        )


def _confirm_and_execute(
    session: LoomSession,
    draft: LoomDraft,
    logo: str,
    *,
    confirm_execute: bool,
) -> None:
    try:
        shown = json.dumps(draft.value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        shown = repr(draft.value)
    prompt = f"Execute Loom object_id={draft.reference.object_id!r} value={shown}? "
    if confirm_execute and not vd.confirm(prompt):
        vd.status("Loom execution cancelled; no provider call")
        return
    try:
        references = session.execute_draft(draft)
    except Exception as exc:  # noqa: BLE001 - the provider exception is the visible boundary
        vd.fail(
            f"Loom execute failed for {draft.reference.object_id!r}: "
            f"{type(exc).__name__}: {exc}"
        )
    result = ReferenceSheet(
        session,
        references=references,
        logo=logo,
        confirm_execute=confirm_execute,
    )
    result.reload()
    vd.push(result)


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
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _preview(value: object) -> str:
    if isinstance(value, Mapping):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


ReferenceSheet.addCommand(
    SHIFT_ENTER_KEY,
    "execute-loom-reference",
    "sheet.executeRow(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "execute the complete selected Loom reference",
)
ReferenceSheet.addCommand(
    "B", "show-brand-logo", "sheet.showBrand()", "show selected DIX/ROBA PNG with chafa"
)
DraftSheet.addCommand(
    "e",
    "edit-json-scalar",
    "sheet.editScalar(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "edit the selected JSON-compatible scalar locally",
)
DraftSheet.addCommand(
    "r",
    "replace-json-subtree",
    "sheet.replaceSubtree(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "replace the complete selected JSON-compatible subtree locally",
)
DraftSheet.addCommand(
    SHIFT_ENTER_KEY, "execute-loom-reference", "sheet.executeDraft()", "execute this Loom draft"
)
