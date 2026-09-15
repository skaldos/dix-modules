from __future__ import annotations

from collections.abc import Mapping

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
