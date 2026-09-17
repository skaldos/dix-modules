from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        state: Api,
        ipc: Api,
        active_members: Api,
        navigation_target: Api,
    ) -> None:
        self.context, self.config = context, config
        self.state, self.ipc = state, ipc
        self.active_members, self.navigation_target = active_members, navigation_target
        raw = config.get("state_file", os.environ.get("SKALDOS_SWAY_GROUP_STATE_FILE"))
        if not isinstance(raw, str) or not raw:
            raise ValueError("group state requires state_file or SKALDOS_SWAY_GROUP_STATE_FILE")
        self.path = Path(raw)

    def create(self, group: str) -> None:
        name = _name(group)
        groups, active = self._read()
        if name in groups:
            raise ValueError(f"Sway group already exists: {name}")
        groups[name] = []
        self._write(groups, active)
        self._coordination(groups, active)

    def add(self, group: str) -> bool:
        name = _name(group)
        groups, active = self._read()
        members = _group(groups, name)
        con_id = self._focused()
        if con_id in members:
            return False
        members.append(con_id)
        self._write(groups, active)
        if active == name:
            self._members(members)
        return True

    def remove(self, group: str) -> bool:
        name = _name(group)
        groups, active = self._read()
        members = _group(groups, name)
        con_id = self._focused()
        if con_id not in members:
            return False
        members.remove(con_id)
        self._write(groups, active)
        if active == name:
            self._members(members)
        return True

    def clear(self, group: str) -> bool:
        name = _name(group)
        groups, active = self._read()
        members = _group(groups, name)
        changed = bool(members)
        if changed:
            groups[name] = []
            self._write(groups, active)
        if active == name:
            self._members([])
        return changed

    def show(self, group: str) -> list[int]:
        groups, _ = self._read()
        return list(_group(groups, _name(group)))

    def list(self) -> dict[str, list[int]]:
        groups, _ = self._read()
        return deepcopy(groups)

    def memberships(self) -> list[str]:
        groups, _ = self._read()
        con_id = self._focused()
        return [name for name, members in groups.items() if con_id in members]

    def select(self, group: str) -> bool:
        name = _name(group)
        groups, active = self._read()
        members = _group(groups, name)
        changed = name != active
        if changed:
            self._write(groups, name)
            self._coordination(groups, name)
        self._members(members)
        self._target("group")
        return changed

    def deactivate(self) -> bool:
        groups, active = self._read()
        changed = bool(active)
        self._target("basic")
        if changed:
            self._write(groups, "")
            self._coordination(groups, "")
        self._members([])
        return changed

    def current(self) -> str:
        return self._read()[1]

    def _focused(self) -> int:
        value = self.ipc.require("focused_con_id")()
        if type(value) is not int or value <= 0:
            raise TypeError("focused con_id must be a positive integer")
        return value

    def _members(self, members: list[int]) -> None:
        live_value = self.ipc.require("live_con_ids")()
        if (
            not isinstance(live_value, list)
            or any(type(v) is not int or v <= 0 for v in live_value)
            or len(set(live_value)) != len(live_value)
        ):
            raise TypeError("live con_ids must be unique positive integers")
        live = set(live_value)
        result = self.active_members.require("set")([v for v in members if v in live])
        if result is not None:
            raise TypeError("active members set must return None")

    def _target(self, target: str) -> None:
        result = self.navigation_target.require("set")(target)
        if result is not None:
            raise TypeError("navigation target set must return None")

    def _coordination(self, groups: Mapping[str, list[int]], active: str) -> None:
        result = self.state.require("set")({"groups": list(groups), "active_group": active})
        if type(result) is not bool:
            raise TypeError("ROBA state set must return bool")

    def _read(self) -> tuple[dict[str, list[int]], str]:
        if not self.path.exists():
            return {}, ""
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read Sway group state: {exc}") from exc
        return _validate(value)

    def _write(self, groups: dict[str, list[int]], active: str) -> None:
        checked, active = _validate({"groups": groups, "active_group": active})
        payload = (
            json.dumps(
                {"groups": checked, "active_group": active},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.path.parent, prefix=f".{self.path.name}.", delete=False
            ) as out:
                temporary = out.name
                out.write(payload)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)


def _name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("group name must be a non-empty string")
    normalized = value.strip()
    if "\n" in normalized or "\r" in normalized:
        raise ValueError("group name must occupy exactly one line")
    return normalized


def _group(groups: Mapping[str, list[int]], name: str) -> list[int]:
    if name not in groups:
        raise ValueError(f"unknown Sway group: {name}")
    return groups[name]


def _validate(value: object) -> tuple[dict[str, list[int]], str]:
    if not isinstance(value, Mapping) or set(value) != {"groups", "active_group"}:
        raise TypeError("group state must contain exactly groups and active_group")
    raw = value["groups"]
    if not isinstance(raw, Mapping):
        raise TypeError("groups must be a mapping")
    groups = {}
    for key, members in raw.items():
        name = _name(key)
        if name != key:
            raise ValueError("stored group names must be normalized")
        if not isinstance(members, list) or any(type(v) is not int or v <= 0 for v in members):
            raise TypeError(f"group {name!r} must contain positive integer con_ids")
        if len(set(members)) != len(members):
            raise ValueError(f"group {name!r} contains duplicates")
        groups[name] = list(members)
    active = value["active_group"]
    if not isinstance(active, str) or (active and active not in groups):
        raise ValueError("active_group must be empty or name an existing group")
    return groups, active
