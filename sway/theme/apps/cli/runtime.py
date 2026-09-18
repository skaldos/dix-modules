from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from dix.core.application import ApplicationApi, ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Project the Theme application through the DIX Typer adapter."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        typer: Api,
        theme: ApplicationApi,
    ) -> None:
        self.context, self.config, self.typer = context, config, typer
        self.theme = theme

    def main(self, argv: Sequence[str]) -> int:
        """Invoke the Theme CLI with exactly one application target."""
        result = self.typer.require("invoke")(
            name="dix-sway-theme-cli",
            targets={"theme": self.theme},
            argv=argv,
        )
        if type(result) is not int:
            raise TypeError("Typer invoke must return an integer exit code")
        return result
