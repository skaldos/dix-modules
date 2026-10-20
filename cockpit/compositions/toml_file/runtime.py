from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext


class Runtime:
    """Read exactly one explicit TOML source without retaining a live binding."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def load(self, path: str | Path) -> dict[str, object]:
        source = Path(path)
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.exists():
            raise FileNotFoundError(f"TOML source does not exist: {source}")
        if not source.is_file():
            raise ValueError(f"TOML source is not a regular file: {source}")
        raw = source.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"TOML source is not valid UTF-8: {source}") from exc
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid TOML in {source}: {exc}") from None
