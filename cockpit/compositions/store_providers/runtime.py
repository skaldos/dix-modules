from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Local provider capabilities, not an open object-ID dispatcher."""

    def __init__(self, *, context: CompositionRuntimeContext,
                 config: Mapping[str, object]) -> None:
        self.providers: dict[str, Api] = {}

    def register(self, provider_id: str, provider: Api) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider ID must be non-empty")
        if provider_id in self.providers:
            raise ValueError("provider is already registered")
        for name in ("draft", "validate", "root", "children", "inspect"):
            if not callable(provider.require(name)):
                raise TypeError("provider requires the complete read-only surface")
        self.providers[provider_id] = provider

    def list(self) -> list[str]:
        return sorted(self.providers)

    def call(self, provider_id: str, operation: str, *args: object) -> object:
        if operation not in {"draft", "validate", "root", "children", "inspect"}:
            raise ValueError("unsupported read-only provider operation")
        if provider_id not in self.providers:
            raise ValueError("unknown store provider")
        return copy.deepcopy(self.providers[provider_id].require(operation)(*args))
