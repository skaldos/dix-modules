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
        prepared = _materialize_background_file(document, theme_directory=path.resolve().parent)
        result = self.client_theme.require("execute")(prepared)
        if not isinstance(result, dict):
            raise TypeError("client Theme Knot must return a dictionary")


def _materialize_background_file(
    document: dict[str, object],
    *,
    theme_directory: Path,
) -> dict[str, object]:
    background = document.get("background")
    if not isinstance(background, dict) or background.get("type") != "image":
        return document
    file = background.get("file")
    if not isinstance(file, str) or not file or Path(file).is_absolute():
        return document

    prepared = dict(document)
    prepared_background = dict(background)
    prepared_background["file"] = str((theme_directory / file).resolve())
    prepared["background"] = prepared_background
    return prepared
