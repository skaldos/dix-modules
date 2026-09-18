from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Expose window-list navigation and binding with one repeated ``--ids`` input."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        windows_list_nav: Api,
        binding: Api,
    ) -> None:
        self.context, self.config = context, config
        self.windows_list_nav, self.binding = windows_list_nav, binding

    def set(self, ids: list[int] | None = None) -> None:
        result = self.binding.require("set_windows_list_nav")(_values(ids))
        if result is not None:
            raise TypeError("set_windows_list_nav must return None")

    def left(self, ids: list[int] | None = None) -> dict[str, object]:
        return self._move("left", ids)

    def right(self, ids: list[int] | None = None) -> dict[str, object]:
        return self._move("right", ids)

    def up(self, ids: list[int] | None = None) -> dict[str, object]:
        return self._move("up", ids)

    def down(self, ids: list[int] | None = None) -> dict[str, object]:
        return self._move("down", ids)

    def _move(self, direction: str, ids: list[int] | None) -> dict[str, object]:
        result = self.windows_list_nav.require(direction)(_values(ids))
        if not isinstance(result, dict):
            raise TypeError("window-list navigation result must be a dictionary")
        return dict(result)


def _values(value: list[int] | None) -> list[int]:
    return [] if value is None else value
