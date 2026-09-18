from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Materialize one complete navigation argument route in Sway."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        ipc: Api,
    ) -> None:
        self.context, self.config, self.ipc = context, config, ipc

    def set_basic_nav(self) -> None:
        """Select parameter-free native Sway navigation."""
        self._command("set $dix_sway_nav basic")

    def set_windows_list_nav(self, window_ids: list[int]) -> None:
        """Select window-list navigation with one complete validated ID list."""
        values = _ids(window_ids)
        suffix = "" if not values else " " + " ".join(str(value) for value in values)
        self._command(f"set $dix_sway_nav windows-list{suffix}")

    def _command(self, value: str) -> None:
        result = self.ipc.require("command")(value)
        if result is not None:
            raise TypeError("ipc command must return None")


def _ids(value: object) -> list[int]:
    if not isinstance(value, list):
        raise TypeError("window_ids must be a list")
    result: list[int] = []
    for raw in value:
        if type(raw) is not int or raw <= 0:
            raise TypeError("window_ids must contain positive integers")
        result.append(raw)
    if len(result) != len(set(result)):
        raise ValueError("window_ids must not contain duplicates")
    return result
