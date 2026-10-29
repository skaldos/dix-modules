from __future__ import annotations

import copy
import re
from collections.abc import Mapping


class BrowserSession:
    """A pane-local stack. Catalog and provider calls are explicit, never background sync."""

    def __init__(self, catalog, session: str):
        self.catalog, self.session = catalog, session
        self.store_id = None
        self.stack = []
        self.rows = []
        self.error = ""
        self._known = []

    @property
    def breadcrumb(self):
        return self.safe("/" + " / ".join(
            ([self.store_id] if self.store_id is not None else [])
            + [node["label"] for node in self.stack]))

    def reload(self):
        try:
            self._known = self.catalog.require("list")(self.session)
            if self.store_id is None:
                rows = [{"label": e["store_id"], "kind": e["provider"], "container": True,
                         "path": [], "value": None} for e in self._known]
            else:
                entry = self.catalog.require("get")(self.store_id, self.session)
                path = self.stack[-1]["path"] if self.stack else []
                if not path:
                    self.catalog.require("provider_call")(
                        entry["provider"], "root", entry["connection"])
                rows = self.catalog.require("provider_call")(
                    entry["provider"], "children", entry["connection"], path)
            self.rows, self.error = copy.deepcopy(rows), ""
        except Exception as exc:  # noqa: BLE001 - keep a provider error local to this pane
            self.rows, self.error = [], self.safe(f"{type(exc).__name__}: {exc}")
        return self.rows

    def open(self, node):
        if self.store_id is None:
            self.store_id = node["label"]
        else:
            self.stack.append(copy.deepcopy(node))
        self.reload()

    def parent(self):
        if self.stack:
            self.stack.pop()
        else:
            self.store_id = None
        self.reload()

    def root(self):
        self.stack.clear()
        self.store_id = None
        self.reload()

    def inspect(self, node):
        entry = self.catalog.require("get")(self.store_id, self.session)
        return self.catalog.require("provider_call")(
            entry["provider"], "inspect", entry["connection"], node["path"])

    def safe(self, message: str, extra: object = None):
        def scrub(text, value):
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if "token" in str(key).lower() and isinstance(item, str) and item:
                        text = text.replace(item, "[redacted]")
                    else:
                        text = scrub(text, item)
            elif isinstance(value, list):
                for item in value:
                    text = scrub(text, item)
            return text
        return re.sub(r"roba(?:-control)?1\.[A-Za-z0-9_.-]+", "[redacted]",
                      scrub(scrub(message, self._known), extra)).replace("\n", " ")


class SelectedBrowserSession(BrowserSession):
    """One saved Store only. A changed definition requires an explicit workspace reopen."""

    def __init__(self, catalog, session, store_id):
        super().__init__(catalog, session)
        record = catalog.require("record")(store_id, session)
        self.store_id = store_id
        self.revision = record["revision"]
        self._known = [record["definition"]]

    def _entry(self):
        record = self.catalog.require("record")(self.store_id, self.session)
        if record["revision"] != self.revision:
            raise RuntimeError("Store definition changed; reopen it from the master catalog")
        return record["definition"]

    def reload(self):
        try:
            entry = self._entry()
            path = self.stack[-1]["path"] if self.stack else []
            if not path:
                self.catalog.require("provider_call")(entry["provider"], "root", entry["connection"])
            rows = self.catalog.require("provider_call")(
                entry["provider"], "children", entry["connection"], path)
            self.rows, self.error = copy.deepcopy(rows), ""
        except Exception as exc:  # noqa: BLE001 - keep errors inside the read-only pane
            self.rows, self.error = [], self.safe(f"{type(exc).__name__}: {exc}")
        return self.rows

    def open(self, node):
        self.stack.append(copy.deepcopy(node))
        self.reload()

    def parent(self):
        if self.stack:
            self.stack.pop()
        self.reload()

    def root(self):
        self.stack.clear()
        self.reload()

    def inspect(self, node):
        entry = self._entry()
        return self.catalog.require("provider_call")(
            entry["provider"], "inspect", entry["connection"], node["path"])
