from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


class LayoutDefinitionError(ValueError):
    """Invalid source-declared layout, not missing provider state."""


@dataclass(frozen=True)
class Layout:
    id: str
    sets: object

    def __post_init__(self):
        object.__setattr__(self, "sets", MappingProxyType(dict(self.sets)))

    def describe(self):
        return {"id": self.id, "sets": {role: dataset.describe() for role, dataset in self.sets.items()}}


class Runtime:
    def __init__(self, *, context, config, owner):
        if set(config) != {"model"} or type(config["model"]) is not str or not config["model"].strip():
            raise LayoutDefinitionError("Layout config requires an owner-relative model file")
        root = Path(context.config_base_dir).resolve()
        relative = Path(config["model"])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise LayoutDefinitionError("Layout model must remain inside its owner directory")
        try:
            with path.open("rb") as stream:
                document = tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise LayoutDefinitionError("Cannot load layout source") from exc
        if set(document) != {"layout", "sets"}:
            raise LayoutDefinitionError("Layout requires exactly layout and sets")
        header, sets = document["layout"], document["sets"]
        if not isinstance(header, dict) or set(header) != {"id"}:
            raise LayoutDefinitionError("Layout header requires exactly id")
        self._id = header["id"]
        if type(self._id) is not str or not self._id.strip():
            raise LayoutDefinitionError("Layout id must be non-empty")
        if not isinstance(sets, dict) or not sets:
            raise LayoutDefinitionError("Layout requires a non-empty sets table")
        self._sets = {}
        for role, alias in sets.items():
            if type(role) is not str or not role.strip() or type(alias) is not str or not alias.isidentifier():
                raise LayoutDefinitionError("Set requires a name and a flat dataset alias")
            self._sets[role] = owner.bind_dependency(alias, "definition")
        self._definition = None

    def definition(self) -> object:
        if self._definition is None:
            sets = {}
            for role, get_definition in self._sets.items():
                dataset = get_definition()
                # Local Dataset contract, deliberately not a global class identity/registry.
                if not hasattr(dataset, "fields") or not callable(getattr(dataset, "describe", None)):
                    raise LayoutDefinitionError("Set dependency does not return a Dataset definition")
                sets[role] = dataset
            self._definition = Layout(self._id, sets)
        return self._definition

    def describe(self) -> dict[str, object]:
        return self.definition().describe()
