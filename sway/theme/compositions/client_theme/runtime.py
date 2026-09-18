from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class SwayClientThemeError(ValueError):
    """Raised when a direct client-theme effect input is unsafe or incomplete."""


_FIELDS = ("border", "background", "text", "indicator", "child_border")
_FOCUSED_TAB_TITLE_FIELDS = ("border", "background", "text")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")


class Runtime:
    """Expose safe individual Sway client-color effects."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        client_colors: Api,
        focused_tab_title_colors: Api,
        ipc: Api,
        knot: Api,
    ) -> None:
        self.context, self.config = context, config
        self.client_colors = client_colors
        self.focused_tab_title_colors = focused_tab_title_colors
        self.ipc, self.knot = ipc, knot

    def execute(self, value: object) -> dict[str, object]:
        """Apply all known present fields through Client Colors and their public handler."""
        return self.knot.require("execute")(value)

    def set_focused(self, value: object) -> None:
        """Apply one complete focused client color mapping."""
        self._set_client("focused", value)

    def set_focused_inactive(self, value: object) -> None:
        """Apply one complete focused-inactive client color mapping."""
        self._set_client("focused_inactive", value)

    def set_focused_tab_title(self, value: object) -> None:
        """Apply one complete focused-tab-title color mapping."""
        colors = _color_values(
            value,
            fields=_FOCUSED_TAB_TITLE_FIELDS,
            label="Sway focused tab title colors",
            invalid_label="Sway focused tab title color",
        )
        result = self.ipc.require("command")(
            "client.focused_tab_title " + " ".join(colors)
        )
        if result is not None:
            raise TypeError("Sway IPC command must return None")

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
    return _color_values(
        value,
        fields=_FIELDS,
        label="Sway client colors",
        invalid_label="Sway client color",
    )


def _color_values(
    value: object,
    *,
    fields: tuple[str, ...],
    label: str,
    invalid_label: str,
) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        raise SwayClientThemeError(f"{label} must be a mapping")
    missing = sorted(set(fields) - set(value))
    additional = sorted(set(value) - set(fields), key=str)
    if missing:
        raise SwayClientThemeError(f"{label} have missing fields: {', '.join(missing)}")
    if additional:
        raise SwayClientThemeError(
            f"{label} have additional fields: " + ", ".join(map(str, additional))
        )
    result: list[str] = []
    for field in fields:
        color = value[field]
        if not isinstance(color, str) or _COLOR.fullmatch(color) is None:
            raise SwayClientThemeError(f"invalid {invalid_label} for {field}: {color!r}")
        result.append(color)
    return tuple(result)
