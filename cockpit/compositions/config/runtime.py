from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext


class Runtime:
    """Resolve explicit Cockpit paths without mutating process or user state."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def defaults(self) -> dict[str, str]:
        return {
            "catalog_path": str(self.catalog_path()),
            "runtime_root": str(self.runtime_root()),
        }

    def catalog_path(self, value: str | None = None) -> Path:
        selected = value or _optional_string(self.config.get("catalog_path"))
        selected = selected or os.environ.get("DIX_COCKPIT_CATALOG")
        if selected:
            return _absolute(Path(selected))
        config_home = os.environ.get("XDG_CONFIG_HOME")
        root = Path(config_home) if config_home else Path.home() / ".config"
        return _absolute(root / "skaldos" / "cockpit" / "daemons.toml")

    def runtime_root(self, value: str | None = None) -> Path:
        selected = value or _optional_string(self.config.get("runtime_root"))
        selected = selected or os.environ.get("DIX_COCKPIT_RUNTIME_ROOT")
        if selected:
            return _absolute(Path(selected))
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg:
            return _absolute(Path(xdg) / "dix-cockpit")
        return _absolute(Path(tempfile.gettempdir()) / f"dix-cockpit-{os.getuid()}")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Cockpit path configuration must be a non-empty string")
    return value


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
