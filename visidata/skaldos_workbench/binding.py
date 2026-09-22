"""Resolve two small TOML definitions into one explicit get/set binding."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class KeyAccess(Protocol):
    """Read and replace exactly one bound JSON value."""

    def get_key(self) -> object: ...

    def set_key(self, value: object) -> None: ...


@dataclass(frozen=True)
class BoundProfile:
    """One named editable field backed by known get/set operations."""

    name: str
    field: str
    access: KeyAccess

    def read(self) -> object:
        return self.access.get_key()

    def write(self, value: object) -> None:
        self.access.set_key(value)


def bind_profile(access_path: Path, profile_path: Path, access: KeyAccess) -> BoundProfile:
    """Reject unknown contracts rather than execute template-controlled code."""
    access_spec = _table(access_path, "access")
    profile_spec = _table(profile_path, "profile")
    if access_spec != {
        "name": "roba-key",
        "adapter": "dix-roba-cli",
        "get": "get_key",
        "set": "set_key",
    }:
        raise ValueError("unsupported access template in UX V0")
    if set(profile_spec) != {"name", "field", "get", "set"}:
        raise ValueError("profile template requires only name, field, get and set")
    name = profile_spec["name"]
    field = profile_spec["field"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("profile name must be a non-empty string")
    if not isinstance(field, str) or not field.strip():
        raise ValueError("profile field must be a non-empty string")
    if profile_spec["get"] != access_spec["get"] or profile_spec["set"] != access_spec["set"]:
        raise ValueError("profile operation names do not match access template")
    return BoundProfile(name=name, field=field, access=access)


def _table(path: Path, name: str) -> dict[str, object]:
    with path.open("rb") as source:
        document = tomllib.load(source)
    if set(document) != {name} or not isinstance(document[name], dict):
        raise ValueError(f"template must contain only [{name}]")
    return document[name]
