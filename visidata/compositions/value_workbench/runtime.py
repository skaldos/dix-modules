from __future__ import annotations

from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext

from .draft import ValueDraft, parse_toml_literal


class Runtime:
    """Expose provider-neutral local value editing primitives."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def create_draft(self, value: object) -> ValueDraft:
        return ValueDraft(value)

    def parse_toml_literal(self, raw: str) -> object:
        return parse_toml_literal(raw)
