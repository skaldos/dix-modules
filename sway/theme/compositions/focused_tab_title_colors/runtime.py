from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol, cast


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


_FIELDS = ("border", "background", "text")


class Runtime:
    """Compose focused-tab-title colors from the local Sway Color strand."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        color: Api,
        strand: Api,
    ) -> None:
        self.context, self.config = context, config
        self.color, self.strand = color, strand

    def execute(self, value: object) -> dict[str, object]:
        """Validate and materialize one exact three-color mapping."""
        processed = self.strand.require("process_input")(value)
        if not isinstance(processed, dict):
            raise TypeError("Norn model boundary returned a non-dict value")
        validate_color = self.color.require("execute")
        result = {field: validate_color(processed[field]) for field in _FIELDS}
        return cast(dict[str, object], self.strand.require("process_output")(result))
