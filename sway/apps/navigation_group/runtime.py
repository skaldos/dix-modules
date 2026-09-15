from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dix.core.application import ApplicationApi
else:
    ApplicationApi = object


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        basic: ApplicationApi,
        active_members: Api,
        ipc: Api,
    ) -> None:
        self.context, self.config, self.basic, self.active_members, self.ipc = (
            context,
            config,
            basic,
            active_members,
            ipc,
        )

    def left(self) -> dict[str, object]:
        return self._move("left")

    def right(self) -> dict[str, object]:
        return self._move("right")

    def up(self) -> dict[str, object]:
        return self._move("up")

    def down(self) -> dict[str, object]:
        return self._move("down")

    def _move(self, direction: str) -> dict[str, object]:
        members = _ids(self.active_members.require("get")(), "active members")
        if not members:
            return _mapping(self.basic.require(direction)(), "basic navigation")
        origin = _id(self.ipc.require("focused_con_id")(), "focused con_id")
        live_ids = _ids(self.ipc.require("live_con_ids")(), "live con_ids")
        live = set(live_ids)
        stale = [value for value in members if value not in live]
        allowed = set(members) & live
        visited = [origin]
        seen = {origin}
        current = origin
        topology: dict[int, tuple[int | None, list[int], list[int]]] | None = None
        if not any(value != origin for value in allowed):
            return _result(direction, origin, origin, False, True, visited, stale)
        for _ in range(max(1, len(live_ids) + 1)):
            previous = current
            step = _mapping(self.basic.require(direction)(), "basic navigation")
            if step.get("direction") != direction or step.get("origin_id") != current:
                raise ValueError("basic navigation returned an inconsistent step")
            focused = _id(step.get("focused_id"), "step focused con_id")
            changed = step.get("changed")
            if type(changed) is not bool or changed != (focused != current):
                raise ValueError("basic navigation returned invalid changed")
            repeated = focused in seen
            if not repeated:
                seen.add(focused)
                visited.append(focused)
            current = focused
            if focused != origin and focused in allowed:
                return _result(direction, origin, focused, True, False, visited, stale)
            if changed:
                if topology is None:
                    topology = _topology(self.ipc.require("navigation_topology")())
                candidate = _target_branch_candidate(topology, previous, focused, allowed)
                if candidate is not None:
                    value = self.ipc.require("focus_con_id")(candidate)
                    if value is not None:
                        raise TypeError("focus_con_id must return None")
                    actual = _id(self.ipc.require("focused_con_id")(), "directly focused con_id")
                    if actual != candidate:
                        raise RuntimeError(
                            f"Sway direct focus failed: expected {candidate}, got {actual}"
                        )
                    if candidate not in seen:
                        seen.add(candidate)
                        visited.append(candidate)
                    return _result(direction, origin, candidate, True, False, visited, stale)
            if not changed or repeated:
                break
        value = self.ipc.require("focus_con_id")(origin)
        if value is not None:
            raise TypeError("focus_con_id must return None")
        current = _id(self.ipc.require("focused_con_id")(), "restored con_id")
        if current != origin:
            raise RuntimeError(f"Sway focus restore failed: expected {origin}, got {current}")
        return _result(direction, origin, current, False, True, visited, stale)


def _id(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise TypeError(f"{label} must be a positive integer")
    return value


def _ids(value: object, label: str) -> list[int]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result = [_id(v, label) for v in value]
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must return a mapping")
    return value


def _topology(value: object) -> dict[int, tuple[int | None, list[int], list[int]]]:
    if not isinstance(value, list) or not value:
        raise TypeError("navigation topology must be a non-empty list")
    result: dict[int, tuple[int | None, list[int], list[int]]] = {}
    for raw in value:
        node = _mapping(raw, "navigation topology node")
        if set(node) != {"con_id", "parent_id", "children", "focus"}:
            raise ValueError("navigation topology node has invalid fields")
        con_id = _id(node["con_id"], "topology con_id")
        if con_id in result:
            raise ValueError(f"navigation topology contains duplicate con_id {con_id}")
        parent = node["parent_id"]
        if parent is not None:
            parent = _id(parent, "topology parent_id")
        children = _ids(node["children"], "topology children")
        focus = _ids(node["focus"], "topology focus")
        if not set(focus) <= set(children):
            raise ValueError(f"topology focus for {con_id} must reference direct children")
        result[con_id] = (parent, children, focus)
    for con_id, (parent, children, _) in result.items():
        if parent is not None and parent not in result:
            raise ValueError(f"topology node {con_id} references missing parent {parent}")
        for child in children:
            if child not in result:
                raise ValueError(f"topology node {con_id} references missing child {child}")
            if result[child][0] != con_id:
                raise ValueError(f"topology parent edge for {child} is inconsistent")
    return result


def _target_branch_candidate(
    topology: dict[int, tuple[int | None, list[int], list[int]]],
    origin: int,
    focused: int,
    allowed: set[int],
) -> int | None:
    origin_path = _ancestor_path(topology, origin)
    target_path = _ancestor_path(topology, focused)
    origin_ancestors = set(origin_path)
    lca = next((con_id for con_id in target_path if con_id in origin_ancestors), None)
    if lca is None:
        raise ValueError(f"topology has no common ancestor for {origin} and {focused}")
    target_to_lca = target_path[: target_path.index(lca)]
    if not target_to_lca:
        return None
    branch = target_to_lca[-1]
    return _first_allowed_leaf(topology, branch, allowed, set())


def _ancestor_path(
    topology: dict[int, tuple[int | None, list[int], list[int]]], con_id: int
) -> list[int]:
    if con_id not in topology:
        raise ValueError(f"focused con_id {con_id} is missing from navigation topology")
    result: list[int] = []
    seen: set[int] = set()
    current: int | None = con_id
    while current is not None:
        if current in seen:
            raise ValueError("navigation topology contains a parent cycle")
        if current not in topology:
            raise ValueError(f"navigation topology references missing parent {current}")
        seen.add(current)
        result.append(current)
        current = topology[current][0]
    return result


def _first_allowed_leaf(
    topology: dict[int, tuple[int | None, list[int], list[int]]],
    con_id: int,
    allowed: set[int],
    active: set[int],
) -> int | None:
    if con_id in active:
        raise ValueError("navigation topology contains a child cycle")
    _, children, focus = topology[con_id]
    if not children:
        return con_id if con_id in allowed else None
    active.add(con_id)
    ordered = [*focus, *(child for child in children if child not in set(focus))]
    for child in ordered:
        candidate = _first_allowed_leaf(topology, child, allowed, active)
        if candidate is not None:
            active.remove(con_id)
            return candidate
    active.remove(con_id)
    return None


def _result(direction, origin, focused, matched, restored, visited, stale):
    return {
        "direction": direction,
        "origin_id": origin,
        "focused_id": focused,
        "matched": matched,
        "restored": restored,
        "visited_ids": list(visited),
        "stale_ids": list(stale),
    }
