from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

_THEME_ID = re.compile(rb"[a-z0-9][a-z0-9_-]*\n\Z")
_THEME_VALUE = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")


class Runtime:
    def __init__(self, *, context: object, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config

    def get(self, path: str = "") -> str:
        marker = self._path(path)
        if not marker.exists():
            return ""
        try:
            payload = marker.read_bytes()
        except OSError as exc:
            raise ValueError(f"cannot read active Sway theme: {exc}") from exc
        if _THEME_ID.fullmatch(payload) is None:
            raise ValueError("active Sway theme must be exactly one valid theme ID and newline")
        return payload[:-1].decode("ascii")

    def set(self, theme: str, path: str = "") -> None:
        if not isinstance(theme, str) or _THEME_VALUE.fullmatch(theme) is None:
            raise ValueError(f"invalid Sway theme ID: {theme!r}")
        marker = self._path(path)
        marker.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=marker.parent, prefix=f".{marker.name}.", delete=False
            ) as out:
                temporary = out.name
                out.write(f"{theme}\n".encode("ascii"))
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, marker)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def _path(self, explicit: str) -> Path:
        if not isinstance(explicit, str):
            raise TypeError("active theme path must be a string")
        raw: object = explicit or self.config.get(
            "path", os.environ.get("SKALDOS_SWAY_ACTIVE_THEME_FILE")
        )
        if not isinstance(raw, str) or not raw:
            raise ValueError(
                "active theme path requires path or SKALDOS_SWAY_ACTIVE_THEME_FILE"
            )
        return Path(raw).expanduser().resolve()
