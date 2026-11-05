from __future__ import annotations

import copy
import math
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType


class DatasetDefinitionError(ValueError):
    """Invalid source-declared dataset, not a provider failure."""


class DataspaceNativeValueError(ValueError):
    """A directed input contract did not return finite native storage data."""


def _native_type(value):
    kinds = {str: "string", int: "integer", float: "number", bool: "boolean",
             type(None): "null", list: "array", dict: "object"}
    active = set()

    def visit(item):
        kind = kinds.get(type(item))
        if kind is None or (type(item) is float and not math.isfinite(item)):
            raise DataspaceNativeValueError("Contract output must be finite native data")
        if type(item) in (list, dict):
            if id(item) in active:
                raise DataspaceNativeValueError("Contract output must not contain cycles")
            active.add(id(item))
            if type(item) is dict and any(type(key) is not str for key in item):
                raise DataspaceNativeValueError("Native object keys must be strings")
            for child in item.values() if type(item) is dict else item:
                visit(child)
            active.remove(id(item))
        return kind

    try:
        return visit(value)
    except RecursionError as exc:
        raise DataspaceNativeValueError("Contract output nesting is too deep") from exc


def _load(base_dir, configured):
    if type(configured) is not str or not configured.strip():
        raise DatasetDefinitionError("Dataset model must be an owner-relative file")
    root = Path(base_dir).resolve()
    relative = Path(configured)
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root) or not path.is_file():
        raise DatasetDefinitionError("Dataset model must remain inside its owner directory")
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DatasetDefinitionError("Cannot load dataset source") from exc


def _name(value, label):
    if type(value) is not str or not value.strip():
        raise DatasetDefinitionError(label + " must be a non-empty string")
    return value


@dataclass(frozen=True)
class Field:
    id: str
    contract: str
    operations: tuple[str, ...]
    _input: Callable = field(repr=False)
    _output: Callable = field(repr=False)
    _default: Callable | None = field(default=None, repr=False)

    @property
    def has_default(self):
        return self._default is not None

    def encode(self, value):
        native = self._input(copy.deepcopy(value))
        return _native_type(native), copy.deepcopy(native)

    def decode(self, value):
        return copy.deepcopy(self._output(copy.deepcopy(value)))

    def default_value(self):
        return self._default()

    def describe(self):
        return {"contract": self.contract, "operations": list(self.operations),
                "has_default": self.has_default}


@dataclass(frozen=True)
class Dataset:
    id: str
    fields: Mapping[str, Field]

    def __post_init__(self):
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))

    def describe(self):
        return {"id": self.id, "fields": {key: value.describe() for key, value in self.fields.items()}}


def _default_reader(value):
    # Neither the descriptor nor a returned default exposes the retained mutable snapshot.
    retained = copy.deepcopy(value)
    return lambda: copy.deepcopy(retained)


class Runtime:
    """Bind only the immediate owner's explicit contract aliases; no global lookup."""

    def __init__(self, *, context, config, owner):
        if set(config) != {"model"}:
            raise DatasetDefinitionError("Dataset config requires exactly model")
        document = _load(context.config_base_dir, config["model"])
        if set(document) != {"dataset", "fields"}:
            raise DatasetDefinitionError("Dataset requires exactly dataset and fields")
        header, fields = document["dataset"], document["fields"]
        if not isinstance(header, dict) or set(header) != {"id"}:
            raise DatasetDefinitionError("Dataset header requires exactly id")
        self._id = _name(header["id"], "Dataset id")
        if not isinstance(fields, dict) or not fields:
            raise DatasetDefinitionError("Dataset requires a non-empty fields table")
        self._fields = []
        for name, spec in fields.items():
            _name(name, "Field id")
            if not isinstance(spec, dict) or not {"contract", "operations"} <= set(spec) <= {"contract", "operations", "default"}:
                raise DatasetDefinitionError("Field requires contract, operations and optional default")
            alias = _name(spec["contract"], "Contract alias")
            if not alias.isidentifier():
                raise DatasetDefinitionError("Contract alias must be a flat identifier")
            ops = spec["operations"]
            if type(ops) is not list or any(type(op) is not str for op in ops):
                raise DatasetDefinitionError("Field operations must be a list")
            if len(set(ops)) != len(ops) or not set(ops) <= {"get", "set", "delete"}:
                raise DatasetDefinitionError("Unknown or duplicate field operation")
            bound = Field(name, alias, tuple(ops), owner.bind_dependency(alias, "process_input"),
                          owner.bind_dependency(alias, "process_output"))
            self._fields.append((bound, "default" in spec, copy.deepcopy(spec.get("default"))))
        self._definition = None

    def definition(self) -> object:
        # Deferred owner bindings are finalized by DIX before this explicit phase runs.
        if self._definition is None:
            fields = {}
            for bound, has_default, default in self._fields:
                if has_default:
                    _, native = bound.encode(default)
                    canonical = bound.decode(native)
                    bound = Field(bound.id, bound.contract, bound.operations,
                                  bound._input, bound._output, _default_reader(canonical))
                fields[bound.id] = bound
            self._definition = Dataset(self._id, fields)
        return self._definition

    def describe(self) -> dict[str, object]:
        return self.definition().describe()
