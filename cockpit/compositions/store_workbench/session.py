from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping


class StoreSession:
    """One staged definition. Only save crosses the local catalog boundary."""

    def __init__(self, catalog, values, session="dix"):
        self.catalog, self.values, self.session = catalog, values, session
        self.entries = []
        self.draft = None
        self.baseline = None
        self.original_id = None
        self.path = ()
        self.parents = []
        self.error = ""

    @property
    def dirty(self):
        return self.draft is not None and self.draft.dirty

    def reload_catalog(self):
        self.entries = self.catalog.require("list")(self.session)
        return copy.deepcopy(self.entries)

    def providers(self):
        return self.catalog.require("providers_list")()

    def new(self, provider_id, choose):
        if not self.leave(choose):
            return False
        self._open(self.catalog.require("draft")(provider_id), None)
        return True

    def open(self, store_id, choose):
        if not self.leave(choose):
            return False
        self._open(self.catalog.require("get")(store_id, self.session), store_id)
        return True

    def _open(self, value, original_id):
        self.draft = self.values.require("create_draft")(value)
        self.baseline = copy.deepcopy(value)
        self.original_id = original_id
        self.path, self.parents, self.error = (), [], ""

    def edit(self, path, raw):
        current = self.draft.at(path)
        replacement = atomic(current, raw)
        self.draft.replace(path, replacement)
        self.error = ""

    def save(self):
        if self.draft is None:
            return False
        value = self.draft.at()
        try:
            if self.original_id is None:
                self.catalog.require("create")(value, self.session)
            else:
                self.catalog.require("update")(self.original_id, value, self.session)
        except Exception as exc:  # noqa: BLE001 - explicit secret-redacting boundary
            self.error = self.safe(f"Store save failed: {type(exc).__name__}: {exc}")
            return False
        # Nothing changes baseline until the complete catalog effect succeeds.
        previous_id = self.original_id
        self.original_id = value["store_id"]
        self.baseline = copy.deepcopy(value)
        self.draft = self.values.require("create_draft")(value)
        self.error = ""
        self.entries = [e for e in self.entries if e["store_id"] != previous_id]
        self.entries.append(copy.deepcopy(value))
        self.entries.sort(key=lambda e: e["store_id"])
        return True

    def leave(self, choose):
        if self.dirty:
            decision = choose()
            if decision == "save":
                if not self.save():
                    return False
            elif decision != "discard":
                return False
        self.draft = None
        self.baseline = None
        self.original_id = None
        self.path, self.parents, self.error = (), [], ""
        return True

    def safe(self, message):
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
        data = [self.entries, self.baseline, self.draft.at() if self.draft else None]
        return re.sub(r"roba(?:-control)?1\.[A-Za-z0-9_.-]+", "[redacted]",
                      scrub(str(message), data)).replace("\n", " ")


def atomic(value, raw):
    if not isinstance(raw, str):
        raise TypeError("cell input must be text")
    kind = type(value)
    try:
        if kind is str:
            return raw
        if kind is bool:
            if raw.lower() not in {"true", "false"}:
                raise ValueError
            return raw.lower() == "true"
        if kind is int:
            return int(raw)
        if kind is float:
            result = float(raw)
            if not math.isfinite(result):
                raise ValueError
            return result
    except ValueError:
        # Never echo the input; it can be a misplaced credential.
        raise ValueError(f"cell requires a valid {kind.__name__} value") from None
    raise TypeError("only existing str, int, finite float and true/false bool cells are editable")
