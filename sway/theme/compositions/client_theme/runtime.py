from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class SwayClientThemeError(ValueError):
    """Raised when a direct client-theme effect input is unsafe or incomplete."""


_FIELDS = ("border", "background", "text", "indicator", "child_border")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")


class Runtime:
    """Expose safe individual Sway client-color effects."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        client_colors: Api,
        ipc: Api,
        knot: Api,
    ) -> None:
        self.context, self.config = context, config
        self.client_colors, self.ipc, self.knot = client_colors, ipc, knot

    def execute(self, value: object) -> dict[str, object]:
        """Apply all known present fields through Client Colors and their public handler."""
        return self.knot.require("execute")(value)

    def set_focused(self, value: object) -> None:
        """Apply one complete focused client color mapping."""
        self._set_client("focused", value)

    def set_focused_inactive(self, value: object) -> None:
        """Apply one complete focused-inactive client color mapping."""
        self._set_client("focused_inactive", value)

    def set_unfocused(self, value: object) -> None:
        """Apply one complete unfocused client color mapping."""
        self._set_client("unfocused", value)

    def set_urgent(self, value: object) -> None:
        """Apply one complete urgent client color mapping."""
        self._set_client("urgent", value)

    def _set_client(self, name: str, value: object) -> None:
        colors = _client_colors(value)
        result = self.ipc.require("command")(f"client.{name} " + " ".join(colors))
        if result is not None:
            raise TypeError("Sway IPC command must return None")


def _client_colors(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        raise SwayClientThemeError("Sway client colors must be a mapping")
    missing = sorted(set(_FIELDS) - set(value))
    additional = sorted(set(value) - set(_FIELDS), key=str)
    if missing:
        raise SwayClientThemeError(f"Sway client colors have missing fields: {', '.join(missing)}")
    if additional:
        raise SwayClientThemeError(
            "Sway client colors have additional fields: " + ", ".join(map(str, additional))
        )
    result: list[str] = []
    for field in _FIELDS:
        color = value[field]
        if not isinstance(color, str) or _COLOR.fullmatch(color) is None:
            raise SwayClientThemeError(f"invalid Sway client color for {field}: {color!r}")
        result.append(color)
    return tuple(result)
