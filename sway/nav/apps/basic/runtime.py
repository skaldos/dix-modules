from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Expose basic navigation and its Sway runtime binding as one application API."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        basic_nav: Api,
        binding: Api,
    ) -> None:
        self.context, self.config = context, config
        self.basic_nav, self.binding = basic_nav, binding

    def set(self) -> None:
        result = self.binding.require("set_basic_nav")()
        if result is not None:
            raise TypeError("set_basic_nav must return None")

    def left(self) -> dict[str, object]:
        return self._move("left")

    def right(self) -> dict[str, object]:
        return self._move("right")

    def up(self) -> dict[str, object]:
        return self._move("up")

    def down(self) -> dict[str, object]:
        return self._move("down")

    def _move(self, direction: str) -> dict[str, object]:
        result = self.basic_nav.require(direction)()
        if not isinstance(result, dict):
            raise TypeError("basic navigation result must be a dictionary")
        return dict(result)
