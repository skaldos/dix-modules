from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext

from .session import LoomSession


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Create provider-neutral sessions from owner-bound Loom capabilities."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        values: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.values = values

    def create_session(
        self,
        execute: Callable[[object, str | None], object],
        seed: object,
    ) -> LoomSession:
        """Bind the local capability and resolve the explicit seed once."""
        session = LoomSession(execute, self.values.require("create_draft"))
        session.resolve(seed)
        return session

    def start(
        self,
        execute: Callable[[object, str | None], object],
        seed: object,
        logo: str = "dix",
        confirm_execute: bool = True,
    ) -> int:
        """Resolve the seed and run VisiData without exposing provider selection."""
        from visidata import vd

        from .branding import show_logo
        from .ui import ReferenceSheet

        session = self.create_session(execute, seed)
        show_logo(logo)
        vd.options.disp_menu = False
        sheet = ReferenceSheet(
            session,
            logo=logo,
            confirm_execute=confirm_execute,
        )
        sheet.reload()
        vd.run(sheet)
        return 0
