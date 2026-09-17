from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

_CLIENT_COLOR = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\Z")
_BACKGROUND_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\Z")
_IMAGE_MODES = frozenset({"stretch", "fill", "fit", "center", "tile"})


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object], ipc: Api) -> None:
        self.context, self.config, self.ipc = context, config, ipc

    def set_focused(
        self, border: str, background: str, text: str, indicator: str, child_border: str
    ) -> None:
        self._client("focused", border, background, text, indicator, child_border)

    def set_focused_inactive(
        self, border: str, background: str, text: str, indicator: str, child_border: str
    ) -> None:
        self._client("focused_inactive", border, background, text, indicator, child_border)

    def set_focused_tab_title(self, border: str, background: str, text: str) -> None:
        self._command(
            "client.focused_tab_title "
            + " ".join(_client_color(value) for value in (border, background, text))
        )

    def set_unfocused(
        self, border: str, background: str, text: str, indicator: str, child_border: str
    ) -> None:
        self._client("unfocused", border, background, text, indicator, child_border)

    def set_urgent(
        self, border: str, background: str, text: str, indicator: str, child_border: str
    ) -> None:
        self._client("urgent", border, background, text, indicator, child_border)

    def set_background_file(self, path: str, mode: str, fallback_color: str) -> None:
        if not isinstance(path, str) or not path or any(char in path for char in "\x00\r\n"):
            raise ValueError("background path must be a non-empty single-line string")
        if not Path(path).is_absolute():
            raise ValueError("background path must be absolute")
        if not isinstance(mode, str) or mode not in _IMAGE_MODES:
            raise ValueError(f"unsupported background mode: {mode!r}")
        fallback = _background_color(fallback_color)
        self._command(f"output * bg {json.dumps(path, ensure_ascii=False)} {mode} {fallback}")

    def set_background_color(self, color: str) -> None:
        self._command(f"output * bg {_background_color(color)} solid_color")

    def _client(
        self,
        name: str,
        border: str,
        background: str,
        text: str,
        indicator: str,
        child_border: str,
    ) -> None:
        values = (border, background, text, indicator, child_border)
        self._command(f"client.{name} " + " ".join(_client_color(value) for value in values))

    def _command(self, value: str) -> None:
        result = self.ipc.require("command")(value)
        if result is not None:
            raise TypeError("Sway IPC command must return None")


def _client_color(value: object) -> str:
    if not isinstance(value, str) or _CLIENT_COLOR.fullmatch(value) is None:
        raise ValueError(f"invalid Sway client color: {value!r}")
    return value


def _background_color(value: object) -> str:
    if not isinstance(value, str) or _BACKGROUND_COLOR.fullmatch(value) is None:
        raise ValueError(f"invalid Sway background color: {value!r}")
    return value
