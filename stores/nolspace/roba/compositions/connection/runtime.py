from __future__ import annotations

import copy
import re
from collections.abc import Mapping


class Runtime:
    """Provider-specific bootstrap, separate from the four standardized operations."""

    def __init__(self, *, context, config, loom, access, contract):
        self.loom, self.access, self.contract = loom, access, contract

    def draft(self) -> dict[str, object]:
        return {"context_id": "", "context_locator": "unix:/", "token": "", "timeout": 5.0}

    def validate(self, connection: object) -> dict[str, object]:
        try:
            result = self.loom.require("materialize_connection")(connection)
            fields = {"context_id", "context_locator", "token", "timeout"}
            if set(result) not in (fields, fields | {"instance_id"}):
                raise ValueError("Nolspace requires an explicit existing token-based Context/Instance connection")
            return copy.deepcopy(result)
        except Exception as exc:  # noqa: BLE001 - private credential boundary
            raise ValueError(_safe(f"{type(exc).__name__}: {exc}", connection)) from None

    def root(self, connection: object) -> dict[str, object]:
        conn = self.validate(connection)
        try:
            result = self.access.require("inspect")(
                {"context_locator": conn["context_locator"], "token": conn["token"]}, conn["timeout"])
            if result["context"]["id"] != conn["context_id"]:
                raise ValueError("Context id differs from the authenticated connection")
            if "instance_id" in conn:
                principal = result["principal"]
                rights = principal["access"].get("instance:" + conn["instance_id"], [])
                caps = []
                if principal["owner"] or "read" in rights: caps += ["enumerate", "lookup"]
                if principal["owner"] or "write" in rights: caps += ["upsert", "delete"]
                kind, name = "instance", conn["instance_id"]
            else:
                kind, name, caps = "context", conn["context_id"], ["enumerate", "lookup"]
            return self.contract.require("view")({"name": name, "type": "nolspace", "value": {
                "caps": caps, "target": {"kind": kind, "connection": conn}}})
        except Exception as exc:  # noqa: BLE001 - preserve failure without credentials
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", conn)) from None


def _safe(message, value):
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "token" in str(key).lower() and isinstance(item, str) and item:
                message = message.replace(item, "[redacted]")
            else:
                message = _safe(message, item)
    elif isinstance(value, list):
        for item in value: message = _safe(message, item)
    return re.sub(r"roba(?:-control)?1\.[A-Za-z0-9_.-]+", "[redacted]", message).replace("\n", " ")
