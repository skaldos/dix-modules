from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol, cast


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class SwayBackgroundError(ValueError):
    """Raised when a background does not match one exact supported variant."""


_IMAGE_FIELDS = frozenset({"type", "file", "mode", "fallback_color"})
_COLOR_FIELDS = frozenset({"type", "color"})
_MODES = frozenset({"stretch", "fill", "fit", "center", "tile"})
_RGB = re.compile(r"#[0-9a-fA-F]{6}\Z")


class Runtime:
    """Own the two exact Sway background variants around a structural Strand."""

    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        strand: Api,
    ) -> None:
        self.context, self.config, self.strand = context, config, strand

    def execute(self, value: object) -> dict[str, str]:
        """Validate and return one canonical image or color background."""
        processed = self.strand.require("process_input")(value)
        if not isinstance(processed, dict):
            raise TypeError("Norn object boundary returned a non-dict value")
        normalized = _normalize_background(processed)
        return cast(dict[str, str], self.strand.require("process_output")(normalized))


def _normalize_background(value: Mapping[str, object]) -> dict[str, str]:
    variant = value.get("type")
    if variant == "image":
        _require_exact_fields(value, _IMAGE_FIELDS, variant="image")
        file = value["file"]
        if not isinstance(file, str) or not file or not Path(file).is_absolute():
            raise SwayBackgroundError("image background file must be a non-empty absolute path")
        mode = value["mode"]
        if not isinstance(mode, str) or mode not in _MODES:
            raise SwayBackgroundError(
                "image background mode must be one of: center, fill, fit, stretch, tile"
            )
        fallback = _require_rgb(value["fallback_color"], label="fallback_color")
        return {
            "type": "image",
            "file": file,
            "mode": mode,
            "fallback_color": fallback,
        }
    if variant == "color":
        _require_exact_fields(value, _COLOR_FIELDS, variant="color")
        return {"type": "color", "color": _require_rgb(value["color"], label="color")}
    raise SwayBackgroundError("background type must be exactly 'image' or 'color'")


def _require_exact_fields(
    value: Mapping[str, object],
    fields: frozenset[str],
    *,
    variant: str,
) -> None:
    missing = sorted(fields - set(value))
    additional = sorted(set(value) - fields, key=str)
    if missing:
        raise SwayBackgroundError(
            f"{variant} background has missing fields: {', '.join(missing)}"
        )
    if additional:
        raise SwayBackgroundError(
            f"{variant} background has additional fields: " + ", ".join(map(str, additional))
        )


def _require_rgb(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _RGB.fullmatch(value) is None:
        raise SwayBackgroundError(f"background {label} must use exactly #RRGGBB")
    return value
