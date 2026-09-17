from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

_THEME_ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_CLIENT_COLOR = re.compile(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?\Z")
_BACKGROUND_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\Z")
_CLIENT_FIELDS = {
    "focused": ("border", "background", "text", "indicator", "child_border"),
    "focused_inactive": ("border", "background", "text", "indicator", "child_border"),
    "focused_tab_title": ("border", "background", "text"),
    "unfocused": ("border", "background", "text", "indicator", "child_border"),
    "urgent": ("border", "background", "text", "indicator", "child_border"),
}
_IMAGE_MODES = frozenset({"stretch", "fill", "fit", "center", "tile"})
_TEMPLATE = """[clients.focused]
border = "#4C7899"
background = "#285577"
text = "#FFFFFF"
indicator = "#2E9EF4"
child_border = "#285577"

[clients.focused_inactive]
border = "#333333"
background = "#5F676A"
text = "#FFFFFF"
indicator = "#484E50"
child_border = "#5F676A"

[clients.focused_tab_title]
border = "#333333"
background = "#5F676A"
text = "#FFFFFF"

[clients.unfocused]
border = "#333333"
background = "#222222"
text = "#888888"
indicator = "#292D2E"
child_border = "#222222"

[clients.urgent]
border = "#2F343A"
background = "#900000"
text = "#FFFFFF"
indicator = "#900000"
child_border = "#900000"

[background]
type = "solid_color"
color = "#113344"
"""


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config

    def create(self, theme: str, theme_dir: str = "") -> str:
        root = self._root(theme_dir)
        path = _theme_path(root, theme)
        root.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as out:
            out.write(_TEMPLATE)
        return str(path)

    def list(self, theme_dir: str = "") -> list[str]:
        root = self._root(theme_dir)
        if not root.exists():
            return []
        if not root.is_dir():
            raise NotADirectoryError(f"Sway theme directory is not a directory: {root}")
        result = []
        for path in root.iterdir():
            if path.is_file() and path.suffix == ".toml" and _THEME_ID.fullmatch(path.stem):
                result.append(path.stem)
        return sorted(result)

    def load(self, theme: str, theme_dir: str = "") -> dict[str, object]:
        root = self._root(theme_dir)
        path = _theme_path(root, theme)
        try:
            with path.open("rb") as source:
                raw = tomllib.load(source)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"cannot load Sway theme {theme!r}: {exc}") from exc
        return deepcopy(_validate_theme(theme, path, raw))

    def _root(self, explicit: str) -> Path:
        if not isinstance(explicit, str):
            raise TypeError("theme_dir must be a string")
        raw: object = explicit or self.config.get(
            "theme_dir", os.environ.get("SKALDOS_SWAY_THEME_DIR")
        )
        if not isinstance(raw, str) or not raw:
            raise ValueError("theme directory requires theme_dir or SKALDOS_SWAY_THEME_DIR")
        return Path(raw).expanduser().resolve()


def _theme_path(root: Path, theme: object) -> Path:
    if not isinstance(theme, str) or _THEME_ID.fullmatch(theme) is None:
        raise ValueError(f"invalid Sway theme ID: {theme!r}")
    path = (root / f"{theme}.toml").resolve(strict=False)
    if path.parent != root:
        raise ValueError(f"Sway theme path escapes theme directory: {theme!r}")
    return path


def _validate_theme(theme: str, path: Path, raw: object) -> dict[str, object]:
    value = _mapping(raw, "theme")
    if set(value) not in ({"clients"}, {"clients", "background"}):
        raise ValueError("theme must contain exactly clients and optional background")
    clients_raw = _mapping(value["clients"], "clients")
    if set(clients_raw) != set(_CLIENT_FIELDS):
        raise ValueError("clients contains missing or unknown client classes")
    clients: dict[str, dict[str, str]] = {}
    for client, fields in _CLIENT_FIELDS.items():
        client_raw = _mapping(clients_raw[client], f"clients.{client}")
        if set(client_raw) != set(fields):
            raise ValueError(f"clients.{client} contains missing or unknown fields")
        clients[client] = {
            field: _color(client_raw[field], f"clients.{client}.{field}", _CLIENT_COLOR)
            for field in fields
        }
    background = None
    if "background" in value:
        background = _background(path, value["background"])
    return {
        "id": theme,
        "path": str(path),
        "clients": clients,
        "background": background,
    }


def _background(theme_path: Path, raw: object) -> dict[str, str]:
    value = _mapping(raw, "background")
    kind = value.get("type")
    if kind == "solid_color":
        if set(value) != {"type", "color"}:
            raise ValueError("solid_color background must contain exactly type and color")
        return {
            "type": "solid_color",
            "color": _color(value["color"], "background.color", _BACKGROUND_COLOR),
        }
    if kind == "image":
        if set(value) != {"type", "file", "mode", "fallback_color"}:
            raise ValueError(
                "image background must contain exactly type, file, mode and fallback_color"
            )
        file = value["file"]
        if not isinstance(file, str) or not file or any(char in file for char in "\x00\r\n"):
            raise ValueError("background.file must be a non-empty single-line string")
        mode = value["mode"]
        if not isinstance(mode, str) or mode not in _IMAGE_MODES:
            raise ValueError(f"unsupported background.mode: {mode!r}")
        image = Path(file).expanduser()
        if not image.is_absolute():
            image = theme_path.parent / image
        return {
            "type": "image",
            "file": str(image.resolve(strict=False)),
            "mode": mode,
            "fallback_color": _color(
                value["fallback_color"], "background.fallback_color", _BACKGROUND_COLOR
            ),
        }
    raise ValueError("background.type must be solid_color or image")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError(f"{label} must be a string-keyed table")
    return value


def _color(value: object, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"{label} has an invalid color: {value!r}")
    return value
