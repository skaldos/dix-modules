from __future__ import annotations

import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class SwayThemeApplicationError(ValueError):
    """Raised when a Theme application request violates its file or result contract."""


class Runtime:
    """Load a complete Theme document and delegate it to the client Theme Knot."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        client_theme: Api,
    ) -> None:
        self.context, self.config = context, config
        self.client_theme = client_theme

    def apply(self, file: str) -> None:
        """Parse one complete TOML file before applying its known client Theme fields."""
        if not isinstance(file, str) or not file:
            raise SwayThemeApplicationError("Theme file must be a non-empty string")
        path = Path(file).expanduser()
        if not path.is_file():
            raise SwayThemeApplicationError(f"Theme file is not a regular file: {path}")
        with path.open("rb") as stream:
            document = tomllib.load(stream)
        result = self.client_theme.require("execute")(document)
        if not isinstance(result, dict):
            raise TypeError("client Theme Knot must return a dictionary")
