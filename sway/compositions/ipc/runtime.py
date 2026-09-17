from __future__ import annotations

from collections.abc import Mapping, Sequence

import i3ipc

_DIRECTIONS = frozenset({"left", "right", "up", "down"})


class SwayIpcError(RuntimeError):
    pass


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config

    def focused_con_id(self) -> int:
        try:
            node = i3ipc.Connection().get_tree().find_focused()
        except Exception as exc:
            raise SwayIpcError(f"cannot read focused Sway container: {exc}") from exc
        if node is None:
            raise SwayIpcError("Sway tree has no focused container")
        return _con_id(getattr(node, "id", None), "focused Sway container")

    def focus_direction(self, direction: str) -> None:
        if direction not in _DIRECTIONS:
            raise SwayIpcError(f"unsupported Sway direction: {direction!r}")
        self._command(f"focus {direction}")

    def focus_con_id(self, con_id: int) -> None:
        self._command(f"[con_id={_con_id(con_id, 'Sway container')}] focus")

    def live_con_ids(self) -> list[int]:
        try:
            leaves = i3ipc.Connection().get_tree().leaves()
        except Exception as exc:
            raise SwayIpcError(f"cannot read live Sway containers: {exc}") from exc
        result = [_con_id(getattr(node, "id", None), "Sway tree leaf") for node in leaves]
        if len(set(result)) != len(result):
            raise SwayIpcError("Sway tree contains duplicate con_ids")
        return result

    def navigation_topology(self) -> list[dict[str, object]]:
        """Return a group-free topology for resolving native navigation branches."""
        try:
            tree = i3ipc.Connection().get_tree()
        except Exception as exc:
            raise SwayIpcError(f"cannot read Sway navigation topology: {exc}") from exc
        topology = _normalize_tree(tree)
        _validate_topology(topology)
        return topology

    def command(self, value: str) -> None:
        if not isinstance(value, str) or not value or any(char in value for char in "\x00\r\n"):
            raise SwayIpcError("Sway command must be a non-empty single-line string")
        self._command(value)

    def _command(self, value: str) -> None:
        try:
            replies = i3ipc.Connection().command(value)
        except Exception as exc:
            raise SwayIpcError(f"cannot execute Sway command {value!r}: {exc}") from exc
        if not isinstance(replies, list) or not replies:
            raise SwayIpcError(f"Sway command returned no replies: {value!r}")
        for reply in replies:
            if getattr(reply, "success", None) is not True:
                raise SwayIpcError(f"Sway command failed: {value!r}: {getattr(reply, 'error', '')}")


def _con_id(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise SwayIpcError(f"{label} has no positive integer con_id")
    return value


def _normalize_tree(tree: object) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    active_objects: set[int] = set()

    def visit(node: object, parent_id: int | None) -> None:
        object_id = id(node)
        if object_id in active_objects:
            raise SwayIpcError("Sway tree contains a cycle")
        active_objects.add(object_id)
        con_id = _con_id(getattr(node, "id", None), "Sway tree node")
        regular = _node_sequence(node, "nodes")
        floating = _node_sequence(node, "floating_nodes")
        child_nodes = [*regular, *floating]
        child_ids = [
            _con_id(getattr(child, "id", None), "Sway tree child") for child in child_nodes
        ]
        focus = _id_sequence(getattr(node, "focus", ()), "Sway node focus")
        result.append(
            {
                "con_id": con_id,
                "parent_id": parent_id,
                "children": child_ids,
                "focus": focus,
            }
        )
        for child in child_nodes:
            visit(child, con_id)
        active_objects.remove(object_id)

    visit(tree, None)
    return result


def _node_sequence(node: object, attribute: str) -> list[object]:
    value = getattr(node, attribute, ())
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SwayIpcError(f"Sway node {attribute} must be a sequence")
    return list(value)


def _id_sequence(value: object, label: str) -> list[int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SwayIpcError(f"{label} must be a sequence")
    result = [_con_id(item, label) for item in value]
    if len(result) != len(set(result)):
        raise SwayIpcError(f"{label} must not contain duplicates")
    return result


def _validate_topology(topology: object) -> None:
    if not isinstance(topology, list) or not topology:
        raise SwayIpcError("Sway navigation topology must be a non-empty list")
    nodes: dict[int, tuple[int | None, list[int], list[int]]] = {}
    for raw in topology:
        if not isinstance(raw, Mapping):
            raise SwayIpcError("Sway navigation topology nodes must be mappings")
        if set(raw) != {"con_id", "parent_id", "children", "focus"}:
            raise SwayIpcError("Sway navigation topology node has invalid fields")
        con_id = _con_id(raw["con_id"], "Sway topology node")
        if con_id in nodes:
            raise SwayIpcError(f"Sway navigation topology contains duplicate con_id {con_id}")
        parent = raw["parent_id"]
        if parent is not None:
            parent = _con_id(parent, "Sway topology parent")
        children = _id_sequence(raw["children"], "Sway topology children")
        focus = _id_sequence(raw["focus"], "Sway topology focus")
        nodes[con_id] = (parent, children, focus)

    roots = [con_id for con_id, (parent, _, _) in nodes.items() if parent is None]
    if len(roots) != 1:
        raise SwayIpcError("Sway navigation topology must contain exactly one root")
    referenced_by: dict[int, int] = {}
    for con_id, (_, children, focus) in nodes.items():
        child_set = set(children)
        if not set(focus) <= child_set:
            raise SwayIpcError(f"Sway topology node {con_id} focus must reference direct children")
        for child in children:
            if child not in nodes:
                raise SwayIpcError(f"Sway topology node {con_id} references missing child {child}")
            if child in referenced_by:
                raise SwayIpcError(f"Sway topology node {child} has multiple parents")
            referenced_by[child] = con_id
            if nodes[child][0] != con_id:
                raise SwayIpcError(f"Sway topology parent edge for {child} is inconsistent")

    root = roots[0]
    if root in referenced_by:
        raise SwayIpcError("Sway navigation topology root must not be a child")
    for con_id, (parent, _, _) in nodes.items():
        if con_id == root:
            continue
        if parent is None or referenced_by.get(con_id) != parent:
            raise SwayIpcError(f"Sway topology node {con_id} has an invalid parent edge")

    visited: set[int] = set()
    active: set[int] = set()

    def visit(con_id: int) -> None:
        if con_id in active:
            raise SwayIpcError("Sway navigation topology contains a cycle")
        if con_id in visited:
            return
        active.add(con_id)
        for child in nodes[con_id][1]:
            visit(child)
        active.remove(con_id)
        visited.add(con_id)

    visit(root)
    if visited != set(nodes):
        raise SwayIpcError("Sway navigation topology contains disconnected nodes or a cycle")
