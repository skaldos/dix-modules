from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import ClassVar

from visidata import Column, ItemColumn, Sheet, clipstr_middle, vd


class StoreSheet(Sheet):
    """A single persistent Sheet/stack owner; its local frames never discard a draft."""

    rowtype = "local Store field"
    nKeys = 1
    columns: ClassVar[list] = [Column("key", width=24, keycol=1, getter=lambda c, r: r["key"]),
                              Column("type", width=12, getter=lambda c, r: r["type"]),
                              ItemColumn("value", width=60, type=str)]

    def __init__(self, session, *, logo="dix"):
        self.session, self.logo = session, logo
        super().__init__("Cockpit Stores")
        self.exiting = False
        # Native vd.input subtracts the entire right status from prompt width. General
        # command longnames consume a split Master pane; reserve space locally, not globally.
        vd.options.set("disp_rstatus_fmt", "{sheet.nRows} rows {sheet.modifiedStatus}",
                       obj=type(self))

    @property
    def nHeaderRows(self):
        return 2

    @property
    def breadcrumb(self):
        return self.session.safe("catalog" if self.session.draft is None else
                                 "draft / " + " / ".join(map(str, self.session.path)))

    def drawColHeader(self, scr, y, h, vcolidx):
        col = self.availCols[vcolidx]
        original = col._name
        text = (f"{self.logo.upper()} Stores" + (" DIRTY" if self.session.dirty else "") if vcolidx == 0 else
                ("DIRTY" if self.session.dirty else "clean") if vcolidx == 1 else
                self.session.error or self.breadcrumb)
        col._name = clipstr_middle(text, max(self._visibleColLayout[vcolidx][1]-1, 0))[0] + "\n" + original
        try:
            super().drawColHeader(scr, y, h, vcolidx)
        finally:
            col._name = original

    def reload(self):
        try:
            if self.session.draft is None:
                # The catalog must show provider IDs again after a narrow value-cell view.
                self.cursorVisibleColIndex = self.leftVisibleColIndex = 0
                self.rows = [{"key": row["store_id"], "type": row["provider"], "value": "",
                              "store_id": row["store_id"]} for row in self.session.reload_catalog()]
            else:
                value = self.session.draft.at(self.session.path)
                entries = value.items() if isinstance(value, Mapping) else enumerate(value)
                self.rows = [{"key": str(key), "type": type(item).__name__,
                              "value": display(item), "native": item,
                              "path": self.session.path + (key,)} for key, item in entries]
            self.hasBeenModified = self.session.dirty
            self.name = "Cockpit Stores | " + ("DIRTY" if self.session.dirty else "clean")
            self.cursorRowIndex = min(max(self.cursorRowIndex, 0), max(len(self.rows)-1, 0))
        except Exception as exc:  # noqa: BLE001 - local failure must not kill the pane
            self.session.error = self.session.safe(f"{type(exc).__name__}: {exc}")
            vd.status(self.session.error)

    def choose(self):
        answer = vd.input("Dirty Store: Save / Discard / Cancel [s/d/c]: ",
                          value="c", record=False).strip().lower()
        return {"s": "save", "save": "save", "d": "discard", "discard": "discard"}.get(
            answer, "cancel")

    def enter(self):
        row = self.cursorRow
        if row is None:
            return
        try:
            if self.session.draft is None:
                if self.session.open(row["store_id"], self.choose):
                    self.cursorRowIndex, self.cursorVisibleColIndex = 0, 2
                    self.reload()
            elif isinstance(row["native"], (Mapping, list)):
                self.session.parents.append((self.session.path, self.cursorRowIndex,
                                             self.cursorVisibleColIndex))
                self.session.path = row["path"]
                self.cursorRowIndex, self.cursorVisibleColIndex = 0, 2
                self.reload()
            elif self.cursorCol.name == "value":
                # Native editor, at the drawn value-cell coordinates, no footer/TOML parser.
                raw = self.editCell(value=row["value"], record=False)
                self.session.edit(row["path"], raw)
                self.reload()
        except Exception as exc:  # noqa: BLE001 - preserve baseline and redact bad input
            # Escape is a native ExpectedException; it must not mutate anything.
            self.session.error = self.session.safe(f"{type(exc).__name__}: {exc}")
            vd.status(self.session.error)

    def newStore(self):
        providers = self.session.providers()
        if not providers:
            vd.fail("No Store provider is registered")
        selected = providers[0] if len(providers) == 1 else vd.input(
            "Store provider (" + ", ".join(providers) + "): ", record=False)
        if self.session.new(selected, self.choose):
            self.cursorRowIndex, self.cursorVisibleColIndex = 0, 2
            self.reload()
        self._status_error()

    def saveStore(self):
        saved = self.session.save()
        if saved:
            self.reload()
            vd.status("Store saved locally; no target contacted")
        elif self.session.draft is None:
            vd.status("No Store draft to save")
        self._status_error()
        return saved

    def promptStore(self):
        self.dispatchStore(vd.input(":", record=False))

    def dispatchStore(self, token):
        token = token.strip()
        commands = {"n": self.newStore, "w": self.saveStore, "q": self.exitStore,
                    "r": self.refresh}
        if token in commands:
            commands[token]()
        elif token == "wq":
            if self.saveStore():
                self.exitStore()
        elif token == "q!":
            self.exitStore(discard=True)
        else:
            self.session.error = "Unknown Cockpit command; use n, w, q, wq, q!, r"
            self._status_error()

    def parent(self):
        if self.session.draft is None:
            vd.status("Store catalog stays open; use :q for explicit exit")
        elif self.session.parents:
            path, row, col = self.session.parents.pop()
            self.session.path = path
            self.reload()
            self.cursorRowIndex, self.cursorVisibleColIndex = row, col
        elif self.session.leave(self.choose):
            self.cursorRowIndex = 0
            self.reload()
        self._status_error()

    def refresh(self):
        if self.session.leave(self.choose):
            self.reload()
        self._status_error()

    def exitStore(self, *, discard=False):
        if self.session.leave((lambda: "discard") if discard else self.choose):
            self.hasBeenModified = False
            self.exiting = True
            # Public quit/remove APIs; never patch VisiData's global quit implementation.
            vd.remove(self)
        self._status_error()

    def confirmQuit(self, verb="quit"):
        if not self.session.leave(self.choose):
            vd.fail("Store navigation cancelled")

    def _status_error(self):
        if self.session.error:
            vd.status(self.session.error)


def display(value):
    if isinstance(value, (Mapping, list)):
        return f"[{len(value)} items]" if isinstance(value, list) else f"{{{len(value)} fields}}"
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


# Commands remain local and may be called by the native editor internally. None binds a key
# during import; only configure_store's explicit, process-local allowlist exposes keys.
for name, expr, desc in (
    ("cockpit-store-enter", "sheet.enter()", "drill or edit an atomic value"),
    ("edit-cell", "sheet.enter()", "native editor continuation within the Store"),
    ("cockpit-store-parent", "sheet.parent()", "parent, keep the catalog alive"),
    ("cockpit-store-prompt", "sheet.promptStore()", "closed Cockpit command prompt"),
    ("cockpit-store-save", "sheet.saveStore()", "save the complete local Store"),
    ("cockpit-store-reload", "sheet.refresh()", "guard then reload the catalog"),
):
    StoreSheet.addCommand(None, name, expr, desc, replay=False)


def run_store(sheet):
    """Keep the local draft owned even when native VisiData bypasses Sheet quit commands.

    VisiData 3.4 handles Ctrl+Q directly in its mainloop. Its public run() boundary
    has ended curses at this point; an ordinary terminal prompt is deliberately
    local to this Store application, never a global key/quit monkeypatch.
    """
    from .keymap import StoreKeymapCompatibilityError, configure_store

    while True:
        try:
            sheet.keymap_proof = configure_store(sheet)
        except StoreKeymapCompatibilityError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        sheet._status_error()
        vd.run(sheet)
        if sheet.exiting or not sheet.session.dirty:
            return 0
        try:
            answer = input("Dirty Store after native exit: Save / Discard / Cancel [s/d/c]: ")
        except KeyboardInterrupt:
            answer = "c"
        decision = {"s": "save", "save": "save", "d": "discard", "discard": "discard"}.get(
            answer.strip().lower(), "cancel")
        if sheet.session.leave(lambda decision=decision: decision):
            sheet.exiting = True
            return 0
        # The same controller, path and cursor survive Cancel and failed Save.
        sheet.reload()
