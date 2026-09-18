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
        basic_nav: Api,
        windows_list_nav: Api,
    ) -> None:
        self.context, self.config = context, config
        self.basic_nav, self.windows_list_nav = basic_nav, windows_list_nav

    def left(
        self, strategy: str = "basic", window_ids: list[int] | None = None
    ) -> dict[str, object]:
        return self._move("left", strategy, window_ids)

    def right(
        self, strategy: str = "basic", window_ids: list[int] | None = None
    ) -> dict[str, object]:
        return self._move("right", strategy, window_ids)

    def up(
        self, strategy: str = "basic", window_ids: list[int] | None = None
    ) -> dict[str, object]:
        return self._move("up", strategy, window_ids)

    def down(
        self, strategy: str = "basic", window_ids: list[int] | None = None
    ) -> dict[str, object]:
        return self._move("down", strategy, window_ids)

    def _move(
        self, direction: str, strategy: str, window_ids: list[int] | None
    ) -> dict[str, object]:
        if window_ids is not None and not isinstance(window_ids, list):
            raise TypeError("window_ids must be a list or None")
        if strategy == "basic":
            if window_ids:
                raise ValueError("basic navigation does not accept window IDs")
            value = self.basic_nav.require(direction)()
        elif strategy == "windows-list":
            value = self.windows_list_nav.require(direction)(
                [] if window_ids is None else window_ids
            )
        else:
            raise ValueError(f"unsupported navigation strategy: {strategy!r}")
        if not isinstance(value, dict):
            raise TypeError("navigation result must be a dictionary")
        return dict(value)
