from __future__ import annotations


class Runtime:
    """Four positive operations. The caller explicitly owns the local provider binding."""

    def __init__(self, *, context, config, contract):
        self.contract = contract

    def _view(self, view, operation):
        result = self.contract.require("view")(view)
        if operation not in result["value"]["caps"]:
            raise PermissionError("Nolspace view does not offer " + operation)
        return result

    def enumerate(self, provider: object, view: object) -> list[dict[str, str]]:
        current = self._view(view, "enumerate")
        result = provider.require("enumerate")(current)
        if not isinstance(result, list):
            raise TypeError("Enumeration must return a Reference list")
        refs = [self.contract.require("reference")(item) for item in result]
        if len({ref["name"] for ref in refs}) != len(refs):
            raise ValueError("Duplicate References have no implicit conflict resolution")
        return refs

    def lookup(self, provider: object, view: object, name: str) -> dict[str, object]:
        current = self._view(view, "lookup")
        ref = self.contract.require("reference")({"name": name})
        result = self.contract.require("object")(provider.require("lookup")(current, ref["name"]))
        if result["name"] != name:
            raise ValueError("Lookup returned a different name")
        return result

    def upsert(self, provider: object, view: object, value: object) -> dict[str, object]:
        current = self._view(view, "upsert")
        item = self.contract.require("object")(value)
        result = self.contract.require("object")(provider.require("upsert")(current, item))
        if result["name"] != item["name"]:
            raise ValueError("Upsert returned a different name")
        return result

    def delete(self, provider: object, view: object, name: str) -> dict[str, str]:
        current = self._view(view, "delete")
        ref = self.contract.require("reference")({"name": name})
        result = self.contract.require("reference")(provider.require("delete")(current, ref["name"]))
        if result != ref:
            raise ValueError("Delete returned a different name")
        return result
