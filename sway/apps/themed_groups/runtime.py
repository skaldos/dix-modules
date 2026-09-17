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
        themed_group_files: Api,
        groups: Api,
        themes: Api,
    ) -> None:
        self.context, self.config = context, config
        self.themed_group_files = themed_group_files
        self.groups, self.themes = groups, themes

    def list(self, themed_group_dir: str = "") -> dict[str, str]:
        return self._catalog(themed_group_dir)

    def load(
        self, themed_group_dir: str = "", theme_dir: str = ""
    ) -> dict[str, object]:
        catalog = self._catalog(themed_group_dir)
        for theme in sorted(set(catalog.values())):
            _mapping(self.themes.require("show")(theme, theme_dir), "themes.show")

        groups = _groups(self.groups.require("list")())
        current = self.groups.require("current")()
        if not isinstance(current, str):
            raise TypeError("groups.current must return a string")
        if current and current not in groups:
            raise ValueError("groups.current must be empty or name an existing group")

        managed = sorted(catalog)
        existing = [group for group in managed if group in groups]
        missing = [group for group in managed if group not in groups]
        deactivated = False
        if current in catalog:
            deactivated = _boolean(
                self.groups.require("deactivate")(), "groups.deactivate"
            )

        cleared = []
        for group in existing:
            if _boolean(self.groups.require("clear")(group), "groups.clear"):
                cleared.append(group)

        created = []
        for group in missing:
            _none(self.groups.require("create")(group), "groups.create")
            created.append(group)

        return {
            "managed_groups": managed,
            "created_groups": created,
            "cleared_groups": cleared,
            "deactivated": deactivated,
        }

    def select(
        self,
        group: str,
        themed_group_dir: str = "",
        theme_dir: str = "",
        active_theme_file: str = "",
    ) -> dict[str, object]:
        catalog = self._catalog(themed_group_dir)
        if group not in catalog:
            raise ValueError(f"unknown themed group: {group!r}")
        theme = catalog[group]
        _mapping(self.themes.require("show")(theme, theme_dir), "themes.show")
        changed = _boolean(self.groups.require("select")(group), "groups.select")
        result = _mapping(
            self.themes.require("apply")(theme, theme_dir, active_theme_file),
            "themes.apply",
        )
        return {
            "group": group,
            "theme": theme,
            "group_changed": changed,
            "theme_result": dict(result),
        }

    def _catalog(self, themed_group_dir: str) -> dict[str, str]:
        raw = self.themed_group_files.require("load_all")(themed_group_dir)
        if not isinstance(raw, list):
            raise TypeError("themed_group_files.load_all must return a list")
        catalog = {}
        for item in raw:
            value = _mapping(item, "themed_group_files.load_all item")
            if set(value) != {"id", "path", "group", "theme"}:
                raise TypeError(
                    "themed_group_files.load_all items must contain exactly "
                    "id, path, group and theme"
                )
            if any(not isinstance(value[key], str) for key in value):
                raise TypeError("themed_group_files.load_all item values must be strings")
            group = value["group"]
            theme = value["theme"]
            if group in catalog:
                raise ValueError(f"duplicate themed-group group: {group!r}")
            catalog[group] = theme
        return dict(sorted(catalog.items()))


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must return a mapping")
    return value


def _groups(value: object) -> dict[str, list[int]]:
    raw = _mapping(value, "groups.list")
    groups = {}
    for group, members in raw.items():
        if not isinstance(group, str):
            raise TypeError("groups.list keys must be strings")
        if (
            not isinstance(members, list)
            or any(type(member) is not int or member <= 0 for member in members)
            or len(set(members)) != len(members)
        ):
            raise TypeError("groups.list values must be unique positive integer lists")
        groups[group] = list(members)
    return groups


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must return a boolean")
    return value


def _none(value: object, label: str) -> None:
    if value is not None:
        raise TypeError(f"{label} must return None")
