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
        theme_files: Api,
        theme_ipc: Api,
        active_theme: Api,
    ) -> None:
        self.context, self.config = context, config
        self.theme_files, self.theme_ipc, self.active_theme = (
            theme_files,
            theme_ipc,
            active_theme,
        )

    def create(self, theme: str, theme_dir: str = "") -> str:
        value = self.theme_files.require("create")(theme, theme_dir)
        if not isinstance(value, str) or not value:
            raise TypeError("theme_files.create must return a non-empty path string")
        return value

    def list(self, theme_dir: str = "") -> list[str]:
        value = self.theme_files.require("list")(theme_dir)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise TypeError("theme_files.list must return a list of strings")
        return list(value)

    def list_lines(self, theme_dir: str = "") -> str:
        return "\n".join(self.list(theme_dir))

    def show(self, theme: str, theme_dir: str = "") -> dict[str, object]:
        value = self.theme_files.require("load")(theme, theme_dir)
        return dict(_mapping(value, "theme_files.load"))

    def apply(
        self, theme: str, theme_dir: str = "", active_theme_file: str = ""
    ) -> dict[str, object]:
        loaded = _mapping(self.theme_files.require("load")(theme, theme_dir), "theme_files.load")
        clients = _mapping(loaded.get("clients"), "theme clients")
        self._client("set_focused", clients, "focused")
        self._client("set_focused_inactive", clients, "focused_inactive")
        self._tab_title(clients)
        self._client("set_unfocused", clients, "unfocused")
        self._client("set_urgent", clients, "urgent")
        background = loaded.get("background")
        background_result = "unchanged"
        if background is not None:
            values = _mapping(background, "theme background")
            kind = values.get("type")
            if kind == "solid_color":
                self._none(
                    self.theme_ipc.require("set_background_color")(values.get("color")),
                    "set_background_color",
                )
                background_result = "solid_color"
            elif kind == "image":
                self._none(
                    self.theme_ipc.require("set_background_file")(
                        values.get("file"), values.get("mode"), values.get("fallback_color")
                    ),
                    "set_background_file",
                )
                background_result = "image"
            else:
                raise ValueError(f"unsupported normalized background type: {kind!r}")
        self._none(
            self.active_theme.require("set")(theme, active_theme_file), "active_theme.set"
        )
        path = loaded.get("path")
        if not isinstance(path, str) or not path:
            raise TypeError("theme_files.load path must be a non-empty string")
        return {"theme": theme, "path": path, "background": background_result}

    def current(self, active_theme_file: str = "") -> str:
        value = self.active_theme.require("get")(active_theme_file)
        if not isinstance(value, str):
            raise TypeError("active_theme.get must return a string")
        return value

    def _client(self, function: str, clients: Mapping[str, object], name: str) -> None:
        values = _mapping(clients.get(name), f"theme clients.{name}")
        self._none(
            self.theme_ipc.require(function)(
                values.get("border"),
                values.get("background"),
                values.get("text"),
                values.get("indicator"),
                values.get("child_border"),
            ),
            function,
        )

    def _tab_title(self, clients: Mapping[str, object]) -> None:
        values = _mapping(clients.get("focused_tab_title"), "theme clients.focused_tab_title")
        self._none(
            self.theme_ipc.require("set_focused_tab_title")(
                values.get("border"), values.get("background"), values.get("text")
            ),
            "set_focused_tab_title",
        )

    @staticmethod
    def _none(value: object, label: str) -> None:
        if value is not None:
            raise TypeError(f"{label} must return None")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must return a mapping")
    return value
