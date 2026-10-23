from __future__ import annotations

import copy
import re
from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext


class Runtime:
    """A positive read-only projection. No broad Loom execute capability is delegated."""

    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object],
                 loom, contexts, instances, data, access) -> None:
        self.loom, self.contexts, self.instances = loom, contexts, instances
        self.data, self.access = data, access

    def draft(self) -> dict[str, object]:
        # A normal canonical direct Context connection, not a second credential schema.
        return {"context_id": "", "context_locator": "unix:/", "token": "", "timeout": 5.0}

    def validate(self, connection: object) -> dict[str, object]:
        try:
            value = self.loom.require("materialize_connection")(connection)
        except Exception as exc:  # noqa: BLE001 - redact at the provider boundary
            raise ValueError(redact(f"{type(exc).__name__}: {exc}", connection)) from None
        if "context_locator" not in value and "control_token" not in value:
            raise ValueError("Store requires an existing Context or Control capability")
        return copy.deepcopy(value)

    def root(self, connection: object) -> dict[str, object]:
        self.validate(connection)
        return _node([], "Store", True)

    def children(self, connection: object, path: object) -> list[dict[str, object]]:
        value, parts = self._request(connection, path)
        try:
            if not parts:
                if "control_token" in value:
                    if "context_id" in value:
                        return self._value_children(self._metadata(value), [], "meta")
                    rows = self.contexts.require("native_list")(
                        control_locator=f"unix:{value['control_socket']}",
                        control_token=value["control_token"], timeout=value["timeout"],
                        environment={"ROBA_RUNTIME_ROOT": value["runtime_root"]})
                    return [_node([["context", row["id"]]], row["id"], True)
                            for row in rows]
                return self._scope_children(value, [])
            if parts[0][0] == "context":
                metadata = next((x for x in self._contexts(value)
                                 if x["id"] == parts[0][1]), None)
                if metadata is None:
                    raise ValueError("Context disappeared; reload its parent")
                return self._value_children(metadata, parts, "meta")
            if parts[-1][0] == "instance":
                return self._scope_children(value, parts)
            return self._value_children(self._read(value, parts), parts, "field")
        except Exception as exc:  # noqa: BLE001 - redact at the provider boundary
            raise RuntimeError(redact(f"{type(exc).__name__}: {exc}", value)) from None

    def inspect(self, connection: object, path: object) -> object:
        value, parts = self._request(connection, path)
        try:
            return copy.deepcopy(self._read(value, parts))
        except Exception as exc:  # noqa: BLE001 - redact at the provider boundary
            raise RuntimeError(redact(f"{type(exc).__name__}: {exc}", value)) from None

    def _request(self, connection, path):
        # Validate the entire local path before any transport. No object_id passthrough.
        value = self.validate(connection)
        if not isinstance(path, list) or any(
            not isinstance(p, list) or len(p) != 2 for p in path
        ):
            raise ValueError("invalid read-only Store path")
        kinds = [p[0] for p in path]
        head = []
        if "control_token" in value:
            if "context_id" not in value and kinds[:1] == ["context"]:
                head = ["context"]
            allowed = {"meta", "field", "index"}
        else:
            if "instance_id" not in value and kinds[:1] == ["instance"]:
                head = ["instance"]
            if kinds[len(head):len(head)+1] == ["key"]:
                head += ["key"]
            allowed = {"field", "index"}
            if path and "key" not in head and head != kinds:
                raise ValueError("unsupported read-only Store path")
        if any(k not in allowed for k in kinds[len(head):]):
            raise ValueError("unsupported read-only Store path")
        for kind, item in path:
            if kind == "index":
                if type(item) is not int or item < 0:
                    raise ValueError("invalid value index")
            elif not isinstance(item, str) or not item:
                raise ValueError("invalid read-only path segment")
        return value, copy.deepcopy(path)

    def _contexts(self, value):
        return self.contexts.require("native_list")(
            control_locator=f"unix:{value['control_socket']}",
            control_token=value["control_token"], timeout=value["timeout"],
            environment={"ROBA_RUNTIME_ROOT": value["runtime_root"]})

    def _metadata(self, value):
        return {key: value[key] for key in (
            "context_id", "context_name", "context_created_at", "context_updated_at")}

    def _scope_children(self, value, parts):
        access = {"context_locator": value["context_locator"], "token": value.get("token")}
        scope = value.get("instance_id", "")
        if parts:
            scope = parts[0][1]
        if scope:
            keys = self.data.require("keys")(access=access, instance_id=scope,
                                             timeout=value["timeout"])
            return [_node(parts + [["key", key]], key, True, "key") for key in keys]
        principal = self.access.require("inspect")(access, value["timeout"])["principal"]
        rights = principal.get("access", {})
        context_read = principal.get("owner") is True or "read" in rights.get("context", [])
        nodes = []
        if context_read:
            keys = self.data.require("keys")(access=access, timeout=value["timeout"])
            nodes += [_node([["key", key]], key, True, "key") for key in keys]
            instances = self.instances.require("list")(
                context_access=access, timeout=value["timeout"])
            ids = [i["id"] for i in instances]
        else:
            ids = [r.removeprefix("instance:") for r, caps in rights.items()
                   if r.startswith("instance:") and "read" in caps]
        nodes += [_node([["instance", ident]], ident, True, "instance") for ident in sorted(ids)]
        if not context_read and not ids:
            raise PermissionError("this access has no readable State resources")
        return nodes

    def _read(self, value, parts):
        if "control_token" in value:
            if "context_id" in value:
                result, rest = self._metadata(value), parts
            elif parts and parts[0][0] == "context":
                result = next(x for x in self._contexts(value) if x["id"] == parts[0][1])
                rest = parts[1:]
            else:
                raise ValueError("select one Context metadata entry")
        else:
            scope = value.get("instance_id", "")
            rest = parts
            if rest and rest[0][0] == "instance":
                scope, rest = rest[0][1], rest[1:]
            if not rest or rest[0][0] != "key":
                raise ValueError("select one readable key")
            result = self.data.require("get")(
                access={"context_locator": value["context_locator"], "token": value.get("token")},
                instance_id=scope, key=rest[0][1], timeout=value["timeout"])
            rest = rest[1:]
        for kind, key in rest:
            if (kind in {"field", "meta"} and isinstance(result, dict)
                    or kind == "index" and isinstance(result, list)):
                result = result[key]
            else:
                raise ValueError("value shape changed; reload its parent")
        return result

    @staticmethod
    def _value_children(value, path, mapping_kind):
        if isinstance(value, dict):
            return [_node(path + [[mapping_kind, key]], key,
                          isinstance(item, (dict, list)), type(item).__name__, item)
                    for key, item in value.items()]
        if isinstance(value, list):
            return [_node(path + [["index", i]], str(i), isinstance(item, (dict, list)),
                          type(item).__name__, item) for i, item in enumerate(value)]
        return [_node(path, "value", False, type(value).__name__, value)]


def _node(path, label, container, kind="container", value=None):
    return {"path": path, "label": label, "container": container, "kind": kind, "value": value}


def redact(message: str, value: object) -> str:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if "token" in str(key).lower() and isinstance(item, str) and item:
                message = message.replace(item, "[redacted]")
            else:
                message = redact(message, item)
    elif isinstance(value, list):
        for item in value:
            message = redact(message, item)
    return re.sub(r"roba(?:-control)?1\.[A-Za-z0-9_.-]+", "[redacted]", message)
