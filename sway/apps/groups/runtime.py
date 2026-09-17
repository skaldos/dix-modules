from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(
        self, *, context: ApplicationRuntimeContext, config: Mapping[str, object], groups: Api
    ) -> None:
        self.context, self.config, self.groups = context, config, groups

    def create(self, group: str) -> None:
        return self.groups.require("create")(group)

    def add(self, group: str) -> bool:
        return self.groups.require("add")(group)

    def remove(self, group: str) -> bool:
        return self.groups.require("remove")(group)

    def clear(self, group: str) -> bool:
        return self.groups.require("clear")(group)

    def show(self, group: str) -> list[int]:
        return self.groups.require("show")(group)

    def list(self) -> dict[str, list[int]]:
        return self.groups.require("list")()

    def memberships(self) -> list[str]:
        return self.groups.require("memberships")()

    def select(self, group: str) -> bool:
        return self.groups.require("select")(group)

    def deactivate(self) -> bool:
        return self.groups.require("deactivate")()

    def current(self) -> str:
        return self.groups.require("current")()
