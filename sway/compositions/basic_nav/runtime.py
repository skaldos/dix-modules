from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object], ipc: Api) -> None:
        self.context, self.config, self.ipc = context, config, ipc

    def left(self) -> dict[str, object]:
        return self._move("left")

    def right(self) -> dict[str, object]:
        return self._move("right")

    def up(self) -> dict[str, object]:
        return self._move("up")

    def down(self) -> dict[str, object]:
        return self._move("down")

    def _move(self, direction: str) -> dict[str, object]:
        origin = _id(self.ipc.require("focused_con_id")())
        result = self.ipc.require("focus_direction")(direction)
        if result is not None:
            raise TypeError("focus_direction must return None")
        focused = _id(self.ipc.require("focused_con_id")())
        return {
            "direction": direction,
            "origin_id": origin,
            "focused_id": focused,
            "changed": focused != origin,
        }


def _id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise TypeError("focused con_id must be a positive integer")
    return value
