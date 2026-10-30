from __future__ import annotations

import copy

from .session import BrowserSession


class BoundProvider:
    """A local capability only; Child targets never select another provider."""

    def __init__(self, catalog, provider_id):
        self.catalog, self.provider_id = catalog, provider_id

    def require(self, name):
        if name not in {"enumerate", "lookup", "upsert", "delete"}:
            raise ValueError("Unsupported Nolspace operation")
        return lambda *args: self.catalog.require("provider_call")(self.provider_id, name, *args)


class NolspaceSession:
    """A revision-pinned Store, opaque views and detached, explicitly loaded row caches."""

    def __init__(self, catalog, api, session, store_id):
        self.catalog, self.session = catalog, session
        self.rows, self.error = [], ""
        record = catalog.require("record")(store_id, session)
        self.store_id, self.revision = store_id, record["revision"]
        self._known, self.api = [record["definition"]], api
        self.provider = BoundProvider(catalog, record["definition"]["provider"])
        self.view = None
        self.stack = []

    safe = BrowserSession.safe

    @property
    def breadcrumb(self):
        return self.safe("/" + " / ".join([self.store_id] + [v["name"] for v in self.stack]))

    def _entry(self):
        record = self.catalog.require("record")(self.store_id, self.session)
        if record["revision"] != self.revision:
            raise RuntimeError("Store definition changed; reopen it from the master catalog")
        return record["definition"]

    def require_cap(self, name):
        if self.view is None or name not in self.view["value"]["caps"]:
            raise PermissionError("Nolspace view does not offer " + name)

    def _call(self, name, *args):
        self.require_cap(name)  # Before any provider/target call.
        self._entry()  # Never contact a changed connection from an old window.
        return self.api.require(name)(self.provider, self.view, *args)

    def reload(self):
        try:
            entry = self._entry()
            if self.view is None:
                self.view = self.catalog.require("provider_call")(
                    entry["provider"], "nolspace_root", entry["connection"])
            if "enumerate" in self.view["value"]["caps"]:
                refs = self._call("enumerate")
                self.rows = [{"key": ref["name"], "object": None} for ref in refs]
                self.error = ""
            else:
                self.rows = []
                self.error = "No enumerate capability; use :n to write a known atomic value"
        except Exception as exc:  # noqa: BLE001 - keep the previous confirmed view and cache
            self.error = self.safe(f"{type(exc).__name__}: {exc}")
        return self.rows

    def lookup(self, name):
        item = self._call("lookup", name)
        if item["type"] == "nolspace":
            self.stack.append(copy.deepcopy(item))
            self.view = item
            self.rows = []
            self.reload()
        else:
            self._cache(item)
        return copy.deepcopy(item)

    def _cache(self, item):
        row = next((r for r in self.rows if r["key"] == item["name"]), None)
        if row is None:
            row = {"key": item["name"], "object": None}
            self.rows.append(row)
        row["object"] = copy.deepcopy(item)

    def upsert(self, item):
        result = self._call("upsert", item)
        self._cache(result)  # A write-only result, not a read-after-write.
        self.error = ""
        return result

    def delete(self, name):
        result = self._call("delete", name)
        self.rows = [r for r in self.rows if r["key"] != name]
        self.error = ""
        return result

    def parent(self):
        if self.stack:
            self.stack.pop()
            self.view = self.stack[-1] if self.stack else None
            self.rows = []
        self.reload()

    def root(self):
        self.stack.clear()
        self.view, self.rows = None, []
        self.reload()
