from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType


class MountBindingError(ValueError):
    """Mounts do not exactly bind the layout to explicit local providers and views."""


class UnknownSetError(KeyError):
    """The role is not part of this runtime layout."""


class UnknownFieldError(KeyError):
    """The field is not part of this role's dataset."""


class DatasetOperationError(PermissionError):
    """A dataset does not expose the requested operation."""


@dataclass(frozen=True)
class _Provider:
    _functions: object = field(repr=False)

    def require(self, name):
        return self._functions[name]


@dataclass(frozen=True)
class _Mount:
    view: object = field(repr=False)
    provider: object = field(repr=False)
    caps: tuple[str, ...]


def _view_reader(value):
    retained = copy.deepcopy(value)
    return lambda: copy.deepcopy(retained)


@dataclass(frozen=True)
class _Space:
    _layout: object = field(repr=False)
    _mounts: object = field(repr=False)
    _api: object = field(repr=False)
    _missing: object = field(repr=False)

    def describe(self) -> dict[str, object]:
        description = self._layout.describe()
        required = {"get": "lookup", "set": "upsert", "delete": "delete"}
        for role, dataset in description["sets"].items():
            mount = self._mounts[role]
            dataset["mounted"] = True
            for spec in dataset["fields"].values():
                spec["effective_operations"] = [op for op in spec["operations"] if required[op] in mount.caps]
        return description

    def _field(self, set_id, field_id, operation):
        if type(set_id) is not str or set_id not in self._layout.sets:
            raise UnknownSetError("Unknown Dataspace set")
        dataset = self._layout.sets[set_id]
        if type(field_id) is not str or field_id not in dataset.fields:
            raise UnknownFieldError("Unknown Dataspace field")
        definition = dataset.fields[field_id]
        if operation not in definition.operations:
            raise DatasetOperationError("Dataset does not expose " + operation)
        return definition, self._mounts[set_id]

    def get(self, set_id: str, field_id: str) -> object:
        definition, mount = self._field(set_id, field_id, "get")
        try:
            item = self._api.require("lookup")(mount.provider, mount.view(), field_id)
        except self._missing:
            if definition.has_default:
                return definition.default_value()
            raise
        return definition.decode(item["value"])

    def set(self, set_id: str, field_id: str, value: object) -> object:
        definition, mount = self._field(set_id, field_id, "set")
        kind, native = definition.encode(value)
        item = self._api.require("upsert")(mount.provider, mount.view(),
                                            {"name": field_id, "type": kind, "value": native})
        return definition.decode(item["value"])

    def delete(self, set_id: str, field_id: str) -> dict[str, str]:
        _, mount = self._field(set_id, field_id, "delete")
        self._api.require("delete")(mount.provider, mount.view(), field_id)
        return {"set": set_id, "field": field_id}


class Runtime:
    """Graph-local factory. Returned consumers never need this construction interface."""

    def __init__(self, *, context, config, owner, api, contract):
        if set(config) != {"layout", "providers"}:
            raise MountBindingError("Runtime config requires exactly layout and providers")
        layout, providers = config["layout"], config["providers"]
        if type(layout) is not str or not layout.isidentifier():
            raise MountBindingError("Layout alias must be a flat owner dependency")
        if type(providers) is not list or not providers or any(type(p) is not str or not p.isidentifier() for p in providers):
            raise MountBindingError("Providers must explicitly name flat owner dependencies")
        if len(set(providers)) != len(providers):
            raise MountBindingError("Duplicate provider binding")
        self._layout = owner.bind_dependency(layout, "definition")
        self._providers = {}
        for alias in providers:
            functions = {name: owner.bind_dependency(alias, name)
                         for name in ("enumerate", "lookup", "upsert", "delete")}
            self._providers[alias] = _Provider(MappingProxyType(functions))
        self._api, self._contract = api, contract
        self._missing = contract.require("not_found_type")()

    def materialize(self, mounts: object) -> object:
        layout = self._layout()
        if not hasattr(layout, "sets") or not callable(getattr(layout, "describe", None)):
            raise MountBindingError("Layout dependency does not return a Layout definition")
        if type(mounts) is not list:
            raise MountBindingError("Mount table must be a list of explicit set bindings")
        bound = {}
        for entry in mounts:
            if type(entry) is not dict or set(entry) != {"set", "provider_alias", "nolspace_view"}:
                raise MountBindingError("Mount requires exactly set, provider_alias and nolspace_view")
            role, alias = entry["set"], entry["provider_alias"]
            if type(role) is not str or role not in layout.sets:
                raise MountBindingError("Mount names an unknown layout set")
            if role in bound:
                raise MountBindingError("Duplicate mount for one layout set")
            if type(alias) is not str or alias not in self._providers:
                raise MountBindingError("Mount provider is not an explicitly bound local alias")
            view = self._contract.require("view")(entry["nolspace_view"])
            bound[role] = _Mount(_view_reader(view), self._providers[alias], tuple(view["value"]["caps"]))
        if set(bound) != set(layout.sets):
            raise MountBindingError("Every layout set requires exactly one explicit mount")
        return _Space(layout, MappingProxyType(bound), self._api, self._missing)
