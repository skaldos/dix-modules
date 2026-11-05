from __future__ import annotations

import copy


class Runtime:
    """Counting test provider, never a product backing or implicit runtime fallback."""

    def __init__(self, *, context, config, contract):
        self._missing = contract.require("not_found_type")()
        self._pools, self._settings, self._calls = {}, {}, []

    def _request(self, view, operation, name=None):
        pool = view["value"]["target"]["pool"]
        self._calls.append((operation, pool, name))
        settings = self._settings.get(pool, {})
        if settings.get("error") is not None:
            raise settings["error"]
        return pool, self._pools.setdefault(pool, {}), settings

    def enumerate(self, view: object) -> list:
        _, values, _ = self._request(view, "enumerate")
        return [{"name": name} for name in values]

    def lookup(self, view: object, name: str) -> dict:
        _, values, _ = self._request(view, "lookup", name)
        if name not in values:
            raise self._missing("Test provider key is absent")
        value = copy.deepcopy(values[name])
        kinds = {str: "string", int: "integer", float: "number", bool: "boolean",
                 type(None): "null", list: "array", dict: "object"}
        return {"name": name, "type": kinds[type(value)], "value": value}

    def upsert(self, view: object, value: object) -> dict:
        _, values, settings = self._request(view, "upsert", value["name"])
        values[value["name"]] = copy.deepcopy(value["value"])
        result = copy.deepcopy(value)
        if "canonical" in settings:
            result["value"] = copy.deepcopy(settings["canonical"])
        return result

    def delete(self, view: object, name: str) -> dict:
        _, values, _ = self._request(view, "delete", name)
        values.pop(name, None)
        return {"name": name}

    def configure(self, pool: str, settings: object) -> None:
        self._settings[pool] = dict(settings)
        if "seed" in settings:
            self._pools[pool] = copy.deepcopy(settings["seed"])

    def calls(self) -> list:
        return copy.deepcopy(self._calls)

    def values(self, pool: str) -> dict:
        return copy.deepcopy(self._pools.get(pool, {}))

    def missing_type(self) -> object:
        return self._missing
