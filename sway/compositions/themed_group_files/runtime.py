from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path

_DEFINITION_ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
_THEME_ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config

    def list(self, themed_group_dir: str = "") -> list[str]:
        root = self._root(themed_group_dir)
        if not root.exists():
            return []
        if not root.is_dir():
            raise NotADirectoryError(f"themed-group directory is not a directory: {root}")
        result = []
        for path in root.iterdir():
            if path.is_file() and path.suffix == ".toml":
                if _DEFINITION_ID.fullmatch(path.stem) is None:
                    raise ValueError(f"invalid themed-group definition ID: {path.stem!r}")
                _definition_path(root, path.stem)
                result.append(path.stem)
        return sorted(result)

    def load(self, definition: str, themed_group_dir: str = "") -> dict[str, str]:
        root = self._root(themed_group_dir)
        path = _definition_path(root, definition)
        try:
            with path.open("rb") as source:
                raw = tomllib.load(source)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(
                f"cannot load themed-group definition {definition!r}: {exc}"
            ) from exc
        value = _mapping(raw)
        if set(value) != {"group", "theme"}:
            raise ValueError("themed-group definition must contain exactly group and theme")
        return {
            "id": definition,
            "path": str(path),
            "group": _group(value["group"]),
            "theme": _theme(value["theme"]),
        }

    def load_all(self, themed_group_dir: str = "") -> list[dict[str, str]]:
        result = [self.load(definition, themed_group_dir) for definition in self.list(themed_group_dir)]
        groups = set()
        for value in result:
            group = value["group"]
            if group in groups:
                raise ValueError(f"duplicate themed-group group: {group!r}")
            groups.add(group)
        return [dict(value) for value in result]

    def _root(self, explicit: str) -> Path:
        if not isinstance(explicit, str):
            raise TypeError("themed_group_dir must be a string")
        raw: object = explicit or self.config.get(
            "themed_group_dir", os.environ.get("SKALDOS_SWAY_THEMED_GROUP_DIR")
        )
        if not isinstance(raw, str) or not raw:
            raise ValueError(
                "themed-group directory requires themed_group_dir or "
                "SKALDOS_SWAY_THEMED_GROUP_DIR"
            )
        return Path(raw).expanduser().resolve()


def _definition_path(root: Path, definition: object) -> Path:
    if not isinstance(definition, str) or _DEFINITION_ID.fullmatch(definition) is None:
        raise ValueError(f"invalid themed-group definition ID: {definition!r}")
    path = (root / f"{definition}.toml").resolve(strict=False)
    if path.parent != root:
        raise ValueError(f"themed-group path escapes definition directory: {definition!r}")
    return path


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise TypeError("themed-group definition must be a string-keyed table")
    return value


def _group(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("themed-group group must be a non-empty string")
    if value != value.strip() or "\n" in value or "\r" in value:
        raise ValueError("themed-group group must be normalized and occupy exactly one line")
    return value


def _theme(value: object) -> str:
    if not isinstance(value, str) or _THEME_ID.fullmatch(value) is None:
        raise ValueError(f"invalid themed-group theme ID: {value!r}")
    return value
