from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        windows_list_nav: Api,
        active_members: Api,
    ) -> None:
        self.context, self.config = context, config
        self.windows_list_nav, self.active_members = windows_list_nav, active_members

    def left(self) -> dict[str, object]:
        return self._move("left")

    def right(self) -> dict[str, object]:
        return self._move("right")

    def up(self) -> dict[str, object]:
        return self._move("up")

    def down(self) -> dict[str, object]:
        return self._move("down")

    def _move(self, direction: str) -> dict[str, object]:
        members = self.active_members.require("get")()
        result = self.windows_list_nav.require(direction)(members)
        if not isinstance(result, dict):
            raise TypeError("window-list navigation result must be a dictionary")
        return result
