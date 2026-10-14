from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext

_FIELDS = {"daemon_id", "runtime_root", "logs_root", "timeout"}
_REQUIRED = {"daemon_id", "runtime_root", "logs_root"}


class DaemonCatalogError(ValueError):
    """One daemon catalog cannot be interpreted without guessing."""


class Runtime:
    """Load explicit named daemon roots; never discover or start providers."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def load(self, path: str | Path) -> list[dict[str, object]]:
        catalog_path = Path(path).expanduser().resolve(strict=False)
        try:
            with catalog_path.open("rb") as source:
                document = tomllib.load(source)
        except tomllib.TOMLDecodeError as exc:
            raise DaemonCatalogError(f"invalid daemon catalog {catalog_path}: {exc}") from None
        if set(document) != {"daemons"} or not isinstance(document.get("daemons"), dict):
            raise DaemonCatalogError("daemon catalog must contain exactly one [daemons] table")
        daemons = document["daemons"]
        if not daemons:
            raise DaemonCatalogError("daemon catalog must contain at least one named daemon")
        return [
            _entry(catalog_id, value, catalog_path.parent)
            for catalog_id, value in daemons.items()
        ]


def _entry(catalog_id: object, value: object, base: Path) -> dict[str, object]:
    if not isinstance(catalog_id, str) or not catalog_id.strip():
        raise DaemonCatalogError("catalog IDs must be non-empty strings")
    if not isinstance(value, dict):
        raise DaemonCatalogError(f"daemon {catalog_id!r} must be a TOML table")
    unknown = set(value) - _FIELDS
    missing = _REQUIRED - set(value)
    if unknown:
        raise DaemonCatalogError(
            f"daemon {catalog_id!r} has unknown fields: {', '.join(sorted(unknown))}"
        )
    if missing:
        raise DaemonCatalogError(
            f"daemon {catalog_id!r} is missing fields: {', '.join(sorted(missing))}"
        )
    daemon_id = _string(value, "daemon_id", catalog_id)
    runtime_root = _path(_string(value, "runtime_root", catalog_id), base)
    logs_root = _path(_string(value, "logs_root", catalog_id), base)
    timeout = value.get("timeout", 5.0)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise DaemonCatalogError(f"daemon {catalog_id!r} timeout must be a number")
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise DaemonCatalogError(f"daemon {catalog_id!r} timeout must be finite and positive")
    return {
        "catalog_id": catalog_id,
        "daemon_id": daemon_id,
        "runtime_root": str(runtime_root),
        "logs_root": str(logs_root),
        "timeout": timeout,
    }


def _string(values: Mapping[str, object], field: str, catalog_id: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DaemonCatalogError(f"daemon {catalog_id!r} {field} must be a non-empty string")
    return value


def _path(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve(strict=False)
