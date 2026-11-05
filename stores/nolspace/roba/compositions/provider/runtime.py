from __future__ import annotations

import re
from collections.abc import Mapping

from roba.transport import StateKeyNotFound

_VALUES = frozenset({"string", "integer", "number", "boolean", "null", "array", "object"})


class Runtime:
    """ROBA projection. View caps are hints; authenticated native authority wins each time."""

    def __init__(self, *, context, config, connection, access, data, instances, contract):
        self.connection, self.access, self.data = connection, access, data
        self.instances, self.contract = instances, contract
        self._not_found = contract.require("not_found_type")()

    def _request(self, view, operation):
        try:
            current = self.contract.require("view")(view)
            target = current["value"].get("target")
            if not isinstance(target, dict) or set(target) != {"kind", "connection"}:
                raise ValueError("Invalid ROBA Nolspace target")
            kind = target["kind"]
            if kind not in {"context", "values", "instances", "instance"}:
                raise ValueError("Unknown ROBA Nolspace target kind")
            conn = self.connection.require("validate")(target["connection"])
            if (kind == "instance") != ("instance_id" in conn):
                raise ValueError("ROBA target kind does not match the explicit scope")
            result = self.access.require("inspect")(
                {"context_locator": conn["context_locator"], "token": conn.get("token")}, conn["timeout"])
            if result["context"]["id"] != conn["context_id"]:
                raise ValueError("Context id differs from the authenticated connection")
            principal = result["principal"]
            if operation not in self._caps(kind, conn, principal):
                raise PermissionError("Authenticated ROBA principal does not permit " + operation)
            return kind, conn, principal
        except Exception as exc:  # noqa: BLE001 - never disclose credentials from opaque targets
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", view)) from None

    @staticmethod
    def _caps(kind, conn, principal):
        if kind in {"context", "instances"}:
            return ["enumerate", "lookup"]
        resource = "instance:" + conn["instance_id"] if kind == "instance" else "context"
        rights = principal["access"].get(resource, [])
        caps = []
        if principal["owner"] or "read" in rights: caps += ["enumerate", "lookup"]
        if principal["owner"] or "write" in rights: caps += ["upsert", "delete"]
        return caps

    def _view(self, name, kind, conn, principal):
        return self.contract.require("view")({"name": name, "type": "nolspace", "value": {
            "caps": self._caps(kind, conn, principal), "target": {"kind": kind, "connection": conn}}})

    def _ids(self, conn, principal):
        if principal["owner"] or "read" in principal["access"].get("context", []):
            result = self.instances.require("list")(
                context_access={"context_locator": conn["context_locator"], "token": conn.get("token")},
                timeout=conn["timeout"])
            return [item["id"] for item in result]
        # Known scopes only, not a new native discovery permission. No State read here.
        return sorted(resource.removeprefix("instance:") for resource, rights in principal["access"].items()
                      if resource.startswith("instance:") and set(rights) & {"read", "write", "grant"})

    @staticmethod
    def _args(conn):
        return {"access": {"context_locator": conn["context_locator"], "token": conn.get("token")},
                "instance_id": conn.get("instance_id", ""), "timeout": conn["timeout"]}

    def enumerate(self, view: object) -> list[dict[str, str]]:
        kind, conn, principal = self._request(view, "enumerate")
        try:
            if kind == "context": names = ["values", "instances"]
            elif kind == "instances": names = self._ids(conn, principal)
            else: names = self.data.require("keys")(**self._args(conn))
            return [{"name": name} for name in names]
        except Exception as exc:  # noqa: BLE001 - provider-local error boundary
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", conn)) from None

    def lookup(self, view: object, name: str) -> dict[str, object]:
        self.contract.require("reference")({"name": name})
        kind, conn, principal = self._request(view, "lookup")
        try:
            if kind == "context":
                if name not in {"values", "instances"}: raise KeyError("Unknown structural child")
                return self._view(name, name, conn, principal)
            if kind == "instances":
                if name not in self._ids(conn, principal): raise KeyError("Unknown or inaccessible Instance")
                return self._view(name, "instance", {**conn, "instance_id": name}, principal)
            try:
                value = self.data.require("get")(**self._args(conn), key=name)
            except StateKeyNotFound:
                raise self._not_found("Nolspace key is absent") from None
            types = {str: "string", bool: "boolean", int: "integer", float: "number",
                     type(None): "null", list: "array", dict: "object"}
            return self.contract.require("object")({"name": name, "type": types[type(value)], "value": value})
        except self._not_found:
            raise
        except Exception as exc:  # noqa: BLE001 - no value/token echo in normal error logs
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", conn)) from None

    def upsert(self, view: object, value: object) -> dict[str, object]:
        item = self.contract.require("object")(value)
        if item["type"] not in _VALUES:
            raise ValueError("ROBA Nolspace upsert supports only standard values")
        _, conn, _ = self._request(view, "upsert")
        try:
            self.data.require("set")(**self._args(conn), key=item["name"], value=item["value"])
            return item  # Caller-owned submitted value, never a read-after-write.
        except Exception as exc:  # noqa: BLE001 - provider-local credential redaction
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", conn)) from None

    def delete(self, view: object, name: str) -> dict[str, str]:
        result = self.contract.require("reference")({"name": name})
        _, conn, _ = self._request(view, "delete")
        try:
            self.data.require("delete")(**self._args(conn), key=name)
            return result
        except Exception as exc:  # noqa: BLE001 - provider-local credential redaction
            raise RuntimeError(_safe(f"{type(exc).__name__}: {exc}", conn)) from None


def _safe(message, value):
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "token" in str(key).lower() and isinstance(item, str) and item:
                message = message.replace(item, "[redacted]")
            else: message = _safe(message, item)
    elif isinstance(value, list):
        for item in value: message = _safe(message, item)
    return re.sub(r"roba(?:-control)?1\.[A-Za-z0-9_.-]+", "[redacted]", message).replace("\n", " ")
