from __future__ import annotations

import copy
import json
import math
import os
import re
import subprocess
from typing import ClassVar

from visidata import Column, EscapeException, ItemColumn, Sheet, clipstr_middle, vd

ATOMICS = frozenset({"string", "integer", "number", "boolean", "null"})


def parse_atomic(kind, raw):
    if kind == "string":
        return raw
    if kind == "null" and raw == "null":
        return None
    if kind == "boolean" and raw in {"true", "false"}:
        return raw == "true"
    if kind == "integer" and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw):
        return int(raw)
    if kind == "number":
        value = json.loads(raw)
        if type(value) in (int, float) and math.isfinite(value):
            return value
    raise ValueError("Enter a valid " + kind + " literal (strings need no quotes)")


def cell_text(value):
    return value if type(value) is str else json.dumps(value, ensure_ascii=False, allow_nan=False)


def kind_of(value):
    return {str: "string", int: "integer", float: "number", bool: "boolean",
            type(None): "null", list: "array", dict: "object"}[type(value)]


def preview(value):
    if type(value) is dict:
        return f"{{{len(value)} fields}}"
    if type(value) is list:
        return f"[{len(value)} items]"
    text = cell_text(value)
    return text if len(text) <= 120 else text[:117] + "..."


class NolspaceSheet(Sheet):
    """No ROBA knowledge. Remote Nolspaces and local read-only complex values stay distinct."""

    columns: ClassVar[list] = [Column("key", width=26, getter=lambda c, r: r["key"]),
                              Column("type", width=12, getter=lambda c, r: r["type"]),
                              ItemColumn("value", width=70, type=str)]

    def __init__(self, browser, *, logo="dix"):
        self.browser, self.logo, self.local = browser, logo, []
        super().__init__(f"{logo.upper()} Nolspace")
        vd.options.set("disp_rstatus_fmt", "{sheet.nRows} rows", obj=type(self))

    @property
    def nHeaderRows(self):
        return 2

    @property
    def breadcrumb(self):
        return self.browser.safe(self.browser.breadcrumb + "".join(" / " + name for name, _ in self.local))

    def drawColHeader(self, scr, y, h, vcolidx):
        col = self.availCols[vcolidx]
        original = col._name
        text = (f"{self.logo.upper()} Nolspace" if vcolidx == 0 else
                ("local/read only" if self.local else " / ".join(self.browser.view["value"]["caps"])
                 if self.browser.view else "") if vcolidx == 1 else
                self.browser.error or self.breadcrumb)
        col._name = clipstr_middle(text, max(self._visibleColLayout[vcolidx][1]-1, 0))[0] + "\n" + original
        try:
            super().drawColHeader(scr, y, h, vcolidx)
        finally:
            col._name = original

    def reload(self):
        if not self.local:
            self.browser.reload()
        self.render()

    def render(self):
        if self.local:
            value = self.local[-1][1]
            entries = value.items() if type(value) is dict else enumerate(value)
            self.rows = [{"key": str(k), "type": kind_of(v), "value": preview(v),
                          "object": {"name": str(k), "type": kind_of(v), "value": v}}
                         for k, v in entries]
        else:
            self.rows = [{"key": r["key"], "type": r["object"]["type"] if r["object"] else "",
                          "value": preview(r["object"]["value"]) if r["object"] else "",
                          "object": r["object"]} for r in self.browser.rows]
        self.cursorRowIndex = min(max(self.cursorRowIndex, 0), max(len(self.rows)-1, 0))
        self.name = f"{self.logo.upper()} Nolspace | {self.breadcrumb}"
        if self.browser.error:
            vd.status(self.browser.error)

    def _error(self, exc):
        self.browser.error = self.browser.safe(f"{type(exc).__name__}: {exc}")
        vd.status(self.browser.error)

    def enter(self):
        row = self.cursorRow
        if row is None:
            return
        try:
            item = row["object"]
            if not self.local and self.cursorCol.name == "key":
                item = self.browser.lookup(row["key"])
                self.render()
                if item["type"] == "nolspace":
                    self.cursorRowIndex = self.cursorVisibleColIndex = 0
                else:
                    self.cursorVisibleColIndex = 2
                return
            if item is None:
                raise ValueError("Load this key with Enter before inspecting or editing its value")
            if item["type"] in {"array", "object"}:
                self.local.append((item["name"], copy.deepcopy(item["value"])))
                self.render()
                self.cursorRowIndex = self.cursorVisibleColIndex = 0
            elif not self.local and self.cursorCol.name == "value":
                self.browser.require_cap("upsert")
                if item["type"] not in ATOMICS:
                    raise ValueError("This type is read only")
                raw = self.editCell(value=cell_text(item["value"]), record=False)
                changed = {**item, "value": parse_atomic(item["type"], raw)}
                self.browser.upsert(changed)
                self.render()
        except EscapeException:
            vd.status("Edit cancelled; target unchanged")
        except Exception as exc:  # noqa: BLE001 - parse/provider failure preserves the cache
            self._error(exc)

    def parent(self):
        if self.local:
            self.local.pop()
        else:
            self.browser.parent()
        self.render()
        self.cursorRowIndex = self.cursorVisibleColIndex = 0

    def root(self):
        self.local.clear()
        self.browser.root()
        self.render()
        self.cursorRowIndex = self.cursorVisibleColIndex = 0

    def dispatch(self, token):
        try:
            if token == "n":
                self._mutable("upsert")
                kind = vd.input("Type [string/integer/number/boolean/null]: ", record=False)
                if kind not in ATOMICS:
                    raise ValueError("New values support only standard atomics")
                name = vd.input("Name: ", record=False)
                raw = "null" if kind == "null" else vd.input("Value: ", record=False)
                self.browser.upsert({"name": name, "type": kind, "value": parse_atomic(kind, raw)})
                self.render()
            elif token == "d":
                self._mutable("delete")
                if self.cursorRow is None:
                    raise ValueError("Select a name to delete")
                name = self.cursorRow["key"]
                if vd.confirm("Delete the selected name? "):
                    self.browser.delete(name)
                    self.render()
            elif token == "r":
                self.reload()
            elif token == "q":
                vd.remove(self)
            else:
                raise ValueError("Unknown Nolspace command; use n, d, r, q (no global save)")
        except EscapeException:
            vd.status("Command cancelled; target unchanged")
        except Exception as exc:  # noqa: BLE001 - no target effects on input failure
            self._error(exc)

    def _mutable(self, operation):
        if self.local:
            raise PermissionError("Complex values are local read-only views")
        self.browser.require_cap(operation)

    def prompt(self):
        self.dispatch(vd.input(":", record=False).strip())

    def copy_cell(self):
        try:
            row = self.cursorRow
            if row is None:
                raise ValueError("Select a cell to copy")
            col = self.cursorCol.name
            if col == "value":
                if row["object"] is None:
                    raise ValueError("Value is not loaded; copying never performs a lookup")
                text = cell_text(row["object"]["value"])
            else:
                text = row[col]
            command = os.environ.get("DIX_COCKPIT_CLIPBOARD_COPY")
            if not command:
                raise RuntimeError("Cockpit clipboard adapter is not configured")
            result = subprocess.run([command], input=text, text=True, capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError("Cockpit clipboard adapter failed")
            vd.status("Copied the full cell value")
        except Exception as exc:  # noqa: BLE001 - clipboard errors never echo cell payloads
            self._error(exc)


# No import-time keybindings; the dedicated browser installs its own process allowlist.
for name, expression in (
    ("nolspace-enter", "sheet.enter()"), ("edit-cell", "sheet.enter()"),
    ("nolspace-parent", "sheet.parent()"), ("nolspace-root", "sheet.root()"),
    ("nolspace-prompt", "sheet.prompt()"), ("nolspace-reload", "sheet.reload()"),
    ("nolspace-copy", "sheet.copy_cell()"),
):
    NolspaceSheet.addCommand(None, name, expression, "operate on the current Nolspace", replay=False)
