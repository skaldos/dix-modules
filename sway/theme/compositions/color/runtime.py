from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class SwayColorError(ValueError):
    """Raised when a string is not a supported Sway hexadecimal color."""


_COLOR = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\Z")


class Runtime:
    """Own the Sway-specific color rule around a structural Norn strand."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        strand: Api,
    ) -> None:
        self.context, self.config, self.strand = context, config, strand

    def execute(self, value: object) -> object:
        """Validate and return one unchanged Sway hexadecimal color."""
        processed = self.strand.require("process_input")(value)
        if not isinstance(processed, str):
            raise TypeError("Norn string boundary returned a non-string value")
        if _COLOR.fullmatch(processed) is None:
            raise SwayColorError(
                "Sway color must use exactly #RRGGBB or #RRGGBBAA hexadecimal format"
            )
        return self.strand.require("process_output")(processed)
