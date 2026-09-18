from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from dix.core.application import ApplicationApi, ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Project strategy-specific navigation applications through DIX Typer."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        typer: Api,
        basic: ApplicationApi,
        windows_list: ApplicationApi,
    ) -> None:
        self.context, self.config, self.typer = context, config, typer
        self.basic, self.windows_list = basic, windows_list

    def main(self, argv: Sequence[str]) -> int:
        result = self.typer.require("invoke")(
            name="skaldos-sway-nav",
            targets={"basic": self.basic, "windows-list": self.windows_list},
            argv=argv,
        )
        if type(result) is not int:
            raise TypeError("Typer invoke must return an integer exit code")
        return result
