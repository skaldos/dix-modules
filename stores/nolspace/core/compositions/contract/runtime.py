from __future__ import annotations

import copy
import math
from collections.abc import Mapping

_CAPS = frozenset({"enumerate", "lookup", "upsert", "delete"})


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Nolspace name/type must be a non-empty string")
    return value


def _native(value):
    """Do not coerce names, bools, keys, unknown types or non-finite numbers."""
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _native(item)
        return
    if type(value) is dict and all(isinstance(key, str) for key in value):
        for item in value.values():
            _native(item)
        return
    raise ValueError("Nolspace values must use finite native data types")


class NolspaceNotFoundError(RuntimeError):
    """The requested key is absent, not inaccessible or unparseable."""


class Runtime:
    """Local validation over unchanged Norn boundaries, not a backend or registry."""

    def __init__(self, *, context, config, reference_shape, object_shape):
        self.reference_shape, self.object_shape = reference_shape, object_shape

    def not_found_type(self) -> object:
        """Share the loader-local exception identity through an explicit dependency."""
        return NolspaceNotFoundError

    def reference(self, value: object) -> dict[str, str]:
        if not isinstance(value, Mapping) or set(value) != {"name"}:
            raise ValueError("Reference requires exactly name")
        result = self.reference_shape.require("execute")(dict(value))
        _name(result["name"])
        return copy.deepcopy(result)

    def object(self, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping) or set(value) != {"name", "type", "value"}:
            raise ValueError("Object requires exactly name, type, value")
        result = self.object_shape.require("execute")(dict(value))
        _name(result["name"]); kind = _name(result["type"])
        data = result["value"]
        _native(data)
        standard = {"string": type(data) is str, "integer": type(data) is int,
                    "number": type(data) in (int, float) and not isinstance(data, bool),
                    "boolean": type(data) is bool, "null": data is None,
                    "array": type(data) is list, "object": type(data) is dict}
        if kind in standard and not standard[kind]:
            raise ValueError("Nolspace value does not match its standard type")
        if kind == "nolspace":
            self._view_value(data)
        # Unknown provider type names carry data but acquire no invented editing semantics.
        return copy.deepcopy(result)

    def view(self, value: object) -> dict[str, object]:
        result = self.object(value)
        if result["type"] != "nolspace":
            raise ValueError("View must have type nolspace")
        return result

    @staticmethod
    def _view_value(value):
        if not isinstance(value, dict) or not {"caps"} <= set(value) <= {"caps", "target"}:
            raise ValueError("View value requires caps and optional target")
        caps = value["caps"]
        if not isinstance(caps, list) or any(not isinstance(cap, str) for cap in caps):
            raise ValueError("View capabilities must be a list of standard names")
        if len(set(caps)) != len(caps) or not set(caps) <= _CAPS:
            raise ValueError("Unknown or duplicate Nolspace capability")
        if "target" in value and not isinstance(value["target"], dict):
            raise ValueError("View target must be a provider-opaque object")
