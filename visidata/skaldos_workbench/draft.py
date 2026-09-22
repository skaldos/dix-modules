"""Local JSON draft with explicit whole-value apply."""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence

from .binding import BoundProfile

type PathPart = str | int


class JsonDraft:
    """Hold a detached editable value; backend writes happen only on apply()."""

    def __init__(self, profile: BoundProfile) -> None:
        self.profile = profile
        value = profile.read()
        self._original = copy.deepcopy(value)
        self.value = copy.deepcopy(value)

    @property
    def dirty(self) -> bool:
        return _canonical(self.value) != _canonical(self._original)

    def at(self, path: Sequence[PathPart] = ()) -> object:
        value = self.value
        for part in path:
            if (isinstance(value, dict) and isinstance(part, str)) or (
                isinstance(value, list) and type(part) is int
            ):
                value = value[part]
            else:
                raise KeyError("path does not identify a JSON value")
        return value

    def replace(self, path: Sequence[PathPart], raw_json: str) -> None:
        """Parse a JSON scalar and replace only the selected local leaf."""
        try:
            new = json.loads(raw_json, parse_constant=_reject_constant)
        except ValueError as exc:
            raise ValueError("enter a valid JSON scalar, e.g. \"text\" or 42") from exc
        if isinstance(new, (dict, list)):
            raise TypeError("V0 inline edit accepts only a JSON scalar")
        if not path:
            if isinstance(self.value, (dict, list)):
                raise ValueError("root object/list cannot be replaced inline")
            self.value = new
            return
        parent = self.at(path[:-1])
        part = path[-1]
        if (isinstance(parent, dict) and isinstance(part, str) and part in parent) or (
            isinstance(parent, list) and type(part) is int and 0 <= part < len(parent)
        ):
            if isinstance(parent[part], (dict, list)):
                raise ValueError("open the nested value instead of replacing it inline")
            parent[part] = new
        else:
            raise KeyError("path does not identify an existing JSON leaf")

    def apply(self) -> bool:
        """Write once; keep local changes untouched if the backend raises."""
        if not self.dirty:
            return False
        self.profile.write(copy.deepcopy(self.value))
        self._original = copy.deepcopy(self.value)
        return True


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _reject_constant(_value: str) -> object:
    raise ValueError("non-finite number is not JSON")
