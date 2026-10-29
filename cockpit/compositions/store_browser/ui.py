from __future__ import annotations

import json
from typing import ClassVar

from visidata import ItemColumn, Sheet, clipstr_middle, vd


class StoreSheet(Sheet):
    """Read-only provider navigation, with separate explicit local catalog commands."""

    rowtype = "Store node"
    columns: ClassVar[list] = [ItemColumn("label", width=30), ItemColumn("kind", width=16),
                              ItemColumn("value", width=70)]

    def __init__(self, browser, controller, *, logo="dix", side="A"):
        self.browser, self.controller, self.logo, self.side = browser, controller, logo, side
        super().__init__(f"{logo.upper()} Stores {side}")

    @property
    def nHeaderRows(self):
        return 2

    def drawColHeader(self, scr, y, h, vcolidx):
        col = self.availCols[vcolidx]
        original = col._name
        text = (self.browser.error or self.browser.breadcrumb) if vcolidx else (
            f"{self.logo.upper()} Stores {self.side} · READ ONLY")
        col._name = clipstr_middle(text, max(self._visibleColLayout[vcolidx][1]-1, 0))[0] + "\n" + original
        try:
            super().drawColHeader(scr, y, h, vcolidx)
        finally:
            col._name = original

    def reload(self):
        nodes = self.browser.reload()
        self._render(nodes)

    def _render(self, nodes):
        self.rows = [{**node, "value": _preview(node["value"]), "node": node} for node in nodes]
        self.name = f"{self.logo.upper()} Stores {self.side} | {self.browser.breadcrumb}"
        if self.browser.error:
            vd.status(self.browser.error)
        # Keep cursor valid after empty/error/reloaded results.
        self.cursorRowIndex = min(max(self.cursorRowIndex, 0), max(len(self.rows)-1, 0))

    def openNode(self):
        row = self.cursorRow
        if row is None:
            vd.status("No Store node selected")
            return
        if self.browser.store_id is None or row["node"]["container"]:
            self.browser.open(row["node"])
            self._render(self.browser.rows)
            self.cursorRowIndex = 0
        else:
            try:
                value = self.browser.inspect(row["node"])
                sheet = InspectSheet(value)
                vd.push(sheet)
            except Exception as exc:  # noqa: BLE001 - pane-local read-only boundary
                self.browser.error = self.browser.safe(f"{type(exc).__name__}: {exc}")
                vd.status(self.browser.error)

    def parentNode(self):
        self.browser.parent()
        self._render(self.browser.rows)
        self.cursorRowIndex = 0

    def rootNode(self):
        self.browser.root()
        self._render(self.browser.rows)
        self.cursorRowIndex = 0

    def newStore(self):
        try:
            vd.push(self.controller.new_store(self.browser.session, self.logo))
        except Exception as exc:  # noqa: BLE001 - local Draft errors are not provider effects
            vd.fail(self.browser.safe(f"{type(exc).__name__}: {exc}"))

    def editStore(self):
        ident = self._selected_store()
        value = self.controller.catalog.require("get")(ident, self.browser.session)
        vd.push(self.controller.edit_store(value, session=self.browser.session,
                                          logo=self.logo, original_id=ident))

    def renameStore(self):
        ident = self._selected_store()
        value = self.controller.catalog.require("get")(ident, self.browser.session)
        value["store_id"] = vd.input("New local Store name: ", value=ident, record=False)
        try:
            self.controller.catalog.require("update")(ident, value, self.browser.session)
        except Exception as exc:  # noqa: BLE001 - local catalog boundary
            vd.fail(self.browser.safe(f"{type(exc).__name__}: {exc}", value))
        self.reload()

    def removeStore(self):
        ident = self._selected_store()
        if vd.confirm("Remove only this local Store registration? "):
            self.controller.catalog.require("remove")(ident, self.browser.session)
            self.reload()

    def _selected_store(self):
        if self.browser.store_id is not None:
            return self.browser.store_id
        if self.cursorRow is not None:
            return self.cursorRow["label"]
        vd.fail("No Store selected")


class InspectSheet(Sheet):
    """Local scalar display; no mutation or provider command is bound here."""
    columns: ClassVar[list] = [ItemColumn("value", width=100)]

    def __init__(self, value):
        super().__init__("Read-only Store value")
        self.rows = [{"value": _preview(value)}]


def _preview(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if isinstance(value, list):
        return f"[{len(value)} items]"
    return json.dumps(value, ensure_ascii=False)


for key, name, command, help_text in (
    ("Enter", "open-store-node", "sheet.openNode()", "read a container or inspect a value"),
    ("zB", "store-parent", "sheet.parentNode()", "return to parent or virtual root"),
    ("zU", "store-root", "sheet.rootNode()", "return to the virtual Store root"),
    ("^R", "reload-store", "sheet.reload()", "explicitly reload this pane only"),
    ("zN", "new-store", "sheet.newStore()", "choose a provider and edit a local Store draft"),
    ("zE", "edit-store", "sheet.editStore()", "edit a detached local Store definition"),
    ("zR", "rename-store", "sheet.renameStore()", "rename only a local Store registration"),
    ("zX", "remove-store", "sheet.removeStore()", "remove only a local Store registration"),
):
    StoreSheet.addCommand(key, name, command, help_text)


class ReadOnlyStoreSheet(Sheet):
    """Share rendering/navigation, never inherit the catalog editor's commands or methods."""

    rowtype = "Store node"
    columns: ClassVar[list] = StoreSheet.columns
    nHeaderRows = StoreSheet.nHeaderRows
    drawColHeader = StoreSheet.drawColHeader
    reload = StoreSheet.reload
    _render = StoreSheet._render
    openNode = StoreSheet.openNode
    parentNode = StoreSheet.parentNode
    rootNode = StoreSheet.rootNode

    def __init__(self, browser, *, logo="dix"):
        self.browser, self.logo, self.side = browser, logo, browser.store_id
        super().__init__(f"{logo.upper()} Store · read only")


for key, name, command in (
    ("Enter", "selected-store-enter", "sheet.openNode()"),
    ("q", "selected-store-parent", "sheet.parentNode()"),
    ("zB", "selected-store-back", "sheet.parentNode()"),
    ("zU", "selected-store-root", "sheet.rootNode()"),
    ("^R", "selected-store-reload", "sheet.reload()"),
):
    ReadOnlyStoreSheet.addCommand(key, name, command, "navigate the selected read-only Store")
