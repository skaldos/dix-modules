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
        self.nolspaces: dict[str, tuple[Api, Api]] = {}

    def register(self, provider_id: str, provider: Api) -> None:
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider ID must be non-empty")
        if provider_id in self.providers:
            raise ValueError("provider is already registered")
        for name in ("draft", "validate", "root", "children", "inspect"):
            if not callable(provider.require(name)):
                raise TypeError("provider requires the complete read-only surface")
        self.providers[provider_id] = provider

    def register_nolspace(self, provider_id: str, provider: Api, connection: Api) -> None:
        if provider_id not in self.providers or provider_id in self.nolspaces:
            raise ValueError("Nolspace requires one explicitly registered Store binding")
        for name in ("enumerate", "lookup", "upsert", "delete"):
            if not callable(provider.require(name)):
                raise TypeError("Nolspace provider requires four operations")
        if not callable(connection.require("root")):
            raise TypeError("Nolspace binding requires a local connection bootstrap")
        self.nolspaces[provider_id] = (provider, connection)

    def list(self) -> list[str]:
        return sorted(self.providers)

    def call(self, provider_id: str, operation: str, *args: object) -> object:
        if operation == "nolspace_root" or operation in {"enumerate", "lookup", "upsert", "delete"}:
            if provider_id not in self.nolspaces:
                raise ValueError("Store has no local Nolspace binding")
            provider, connection = self.nolspaces[provider_id]
            function = connection.require("root") if operation == "nolspace_root" else provider.require(operation)
            return copy.deepcopy(function(*args))
        if operation not in {"draft", "validate", "root", "children", "inspect"}:
            raise ValueError("unsupported read-only provider operation")
        if provider_id not in self.providers:
            raise ValueError("unknown store provider")
        return copy.deepcopy(self.providers[provider_id].require(operation)(*args))
