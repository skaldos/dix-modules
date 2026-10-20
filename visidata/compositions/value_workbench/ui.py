from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Mapping
from typing import Any, ClassVar

from visidata.editor import SuspendCurses

from visidata import ItemColumn, Sheet, clipstr_middle, vd

from .branding import show_logo
from .draft import ValueDraft, ValuePath, parse_toml_literal


class ValueSheet(Sheet):
    """Recursively inspect and mutate one provider-neutral local value draft."""

    rowtype = "local value field"
    columns: ClassVar[list[ItemColumn]] = [
        ItemColumn("key", width=26),
        ItemColumn("type", width=16),
        ItemColumn("value", width=76),
    ]

    def __init__(
        self,
        draft: ValueDraft,
        *,
        path: ValuePath = (),
        logo: str = "dix",
        title: str = "TOML value",
    ) -> None:
        self.draft = draft
        self.path = path
        self.logo = logo
        self.value_title = title
        super().__init__(self._title())

    def _title(self) -> str:
        location = ".".join(map(str, self.path)) or "value"
        dirty = "DIRTY" if self.draft.dirty else "clean"
        register = "set" if self.draft.has_register else "empty"
        return (
            f"{self.logo.upper()} local | {self.value_title} | {location} | "
            f"{dirty} | register:{register}"
        )

    @property
    def nHeaderRows(self) -> int:
        """Reserve one persistent context row above the native column labels."""
        return 2

    @property
    def breadcrumb(self) -> str:
        parts = ["value"]
        parts.extend(
            f"[{part}]" if type(part) is int else _single_line(part)
            for part in self.path
        )
        return " › ".join(parts)

    def drawColHeader(self, scr: object, y: int, h: int, vcolidx: int) -> None:
        """Draw live context without adding a selectable synthetic data row."""
        column = self.availCols[vcolidx]
        original_name = column._name
        width = self._visibleColLayout[vcolidx][1]
        context = self._context_header(original_name, width)
        column._name = f"{context}\n{original_name}"
        try:
            super().drawColHeader(scr, y, h, vcolidx)
        finally:
            column._name = original_name

    def _context_header(self, column_name: str, width: int) -> str:
        if column_name == "key":
            text = f"{self.logo.upper()} · {_source_label(self.value_title)}"
        elif column_name == "type":
            dirty = "DIRTY" if self.draft.dirty else "clean"
            register = "set" if self.draft.has_register else "empty"
            text = f"{dirty} · reg:{register}"
        elif column_name == "value":
            text = self.breadcrumb
        else:
            text = ""
        return clipstr_middle(text, max(width - 1, 0))[0]

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
                "part": part,
                "path": self.path + ((part,) if nested else ()),
            }
            for part, item in entries
        ]
        self.name = self._title()

    def openRow(self, row: dict[str, Any]) -> ValueSheet:
        if not isinstance(row["native"], (Mapping, list)):
            vd.fail("scalar value: use e for a TOML-literal replacement")
        sheet = ValueSheet(
            self.draft,
            path=row["path"],
            logo=self.logo,
            title=self.value_title,
        )
        sheet.reload()
        return sheet

    def editScalar(self, row: dict[str, Any]) -> None:
        if isinstance(row["native"], (Mapping, list)):
            vd.fail("container selected: use structural mapping/list commands")
            return
        raw = vd.input(
            "TOML replacement: ",
            value=_toml_literal(row["native"]),
            record=False,
        )
        self._replace(row["path"], raw)

    def addValue(self) -> None:
        current = self.draft.at(self.path)
        if isinstance(current, Mapping):
            key = vd.input("New mapping key: ", record=False)
            raw = vd.input("TOML value: ", record=False)
            try:
                self.draft.add_mapping(self.path, key, parse_toml_literal(raw))
            except (TypeError, ValueError, KeyError, IndexError) as exc:
                vd.fail(str(exc))
                return
            self._changed("mapping entry added")
            return
        if isinstance(current, list):
            raw = vd.input("TOML value to append: ", record=False)
            try:
                self.draft.append_list(self.path, parse_toml_literal(raw))
            except (TypeError, ValueError, KeyError, IndexError) as exc:
                vd.fail(str(exc))
                return
            self._changed("list item appended")
            return
        vd.fail("selected value is neither a mapping nor a list")

    def insertValue(self, row: dict[str, Any]) -> None:
        current = self.draft.at(self.path)
        if not isinstance(current, list) or type(row["part"]) is not int:
            vd.fail("insert requires a selected list item")
            return
        raw = vd.input("TOML value to insert: ", record=False)
        try:
            self.draft.insert_list(self.path, row["part"], parse_toml_literal(raw))
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("list item inserted")

    def renameKey(self, row: dict[str, Any]) -> None:
        current = self.draft.at(self.path)
        if not isinstance(current, Mapping) or not isinstance(row["part"], str):
            vd.fail("rename requires a selected mapping entry")
            return
        new_key = vd.input("New mapping key: ", value=row["part"], record=False)
        try:
            self.draft.rename_mapping(self.path, row["part"], new_key)
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("mapping key renamed")

    def deleteRow(self, row: dict[str, Any]) -> None:
        current = self.draft.at(self.path)
        if not vd.confirm(f"Delete local entry {row['key']!r}? "):
            vd.status("delete cancelled; local draft unchanged")
            return
        try:
            if isinstance(current, Mapping) and isinstance(row["part"], str):
                self.draft.delete_mapping(self.path, row["part"])
            elif isinstance(current, list) and type(row["part"]) is int:
                self.draft.delete_list(self.path, row["part"])
            else:
                vd.fail("delete requires a selected mapping or list entry")
                return
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("local entry deleted")

    def copyRow(self, row: dict[str, Any]) -> None:
        try:
            self.draft.copy_to_register(row["path"])
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self.reload()
        vd.status("selected local subtree copied to register")

    def putReplacement(self, row: dict[str, Any]) -> None:
        try:
            self.draft.put_replacement(row["path"])
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("selected subtree replaced from register")

    def putIntoContainer(self) -> None:
        current = self.draft.at(self.path)
        try:
            if isinstance(current, Mapping):
                key = vd.input("Mapping key for register value: ", record=False)
                self.draft.put_mapping(self.path, key)
            elif isinstance(current, list):
                self.draft.put_list(self.path)
            else:
                vd.fail("register put requires a mapping or list container")
                return
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("register value added to selected container")

    def insertRegister(self, row: dict[str, Any]) -> None:
        current = self.draft.at(self.path)
        if not isinstance(current, list) or type(row["part"]) is not int:
            vd.fail("register insert requires a selected list item")
            return
        try:
            self.draft.put_list(self.path, row["part"])
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("register value inserted into list")

    def showBrand(self) -> None:
        with SuspendCurses():
            show_logo(self.logo)

    def _replace(self, path: ValuePath, raw: str) -> None:
        try:
            self.draft.replace(path, parse_toml_literal(raw))
        except (TypeError, ValueError, KeyError, IndexError) as exc:
            vd.fail(str(exc))
            return
        self._changed("local scalar replaced")

    def _changed(self, message: str) -> None:
        self.reload()
        vd.status(f"{message}; source remains read-only")


def _type_name(value: object) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dt.datetime):
        return "datetime"
    if isinstance(value, dt.date):
        return "date"
    if isinstance(value, dt.time):
        return "time"
    if isinstance(value, Mapping):
        return "mapping"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _single_line(value: object) -> str:
    return " ".join(str(value).splitlines())


def _source_label(value: object) -> str:
    normalized = _single_line(value).replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1] or "value"


def _preview(value: object) -> str:
    if isinstance(value, Mapping):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return _toml_literal(value)


def _toml_literal(value: object) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "-inf" if value < 0 else "inf"
        return repr(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        rendered = value.isoformat()
        return rendered.replace("+00:00", "Z") if isinstance(value, dt.datetime) else rendered
    return repr(value)


ValueSheet.addCommand(
    "e",
    "edit-toml-scalar",
    "sheet.editScalar(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "replace the selected scalar from one TOML literal",
)
ValueSheet.addCommand(
    "a", "add-local-value", "sheet.addValue()", "add a mapping entry or append a list item"
)
ValueSheet.addCommand(
    "i",
    "insert-local-list-value",
    "sheet.insertValue(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "insert a TOML value before the selected list item",
)
ValueSheet.addCommand(
    "r",
    "rename-local-mapping-key",
    "sheet.renameKey(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "rename the selected mapping key without overwriting",
)
ValueSheet.addCommand(
    "d",
    "delete-local-value",
    "sheet.deleteRow(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "delete the selected mapping or list entry after confirmation",
)
ValueSheet.addCommand(
    "y",
    "copy-local-register",
    "sheet.copyRow(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "deep-copy the selected subtree to the session-local register",
)
ValueSheet.addCommand(
    "p",
    "put-local-register-replacement",
    "sheet.putReplacement(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "replace the selected subtree with a deep copy of the register",
)
ValueSheet.addCommand(
    "A",
    "put-local-register-container",
    "sheet.putIntoContainer()",
    "add the register to the current mapping or append it to the current list",
)
ValueSheet.addCommand(
    "I",
    "insert-local-register-list",
    "sheet.insertRegister(cursorRow) if cursorRow is not None else vd.fail('no row selected')",
    "insert the register before the selected list item",
)
ValueSheet.addCommand(
    "B", "show-brand-logo", "sheet.showBrand()", "show selected DIX/ROBA PNG with chafa"
)
