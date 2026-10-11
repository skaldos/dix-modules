from __future__ import annotations

from collections.abc import Callable, Mapping

from dix.core.composition import CompositionRuntimeContext

from .session import LoomSession


class Runtime:
    """Create provider-neutral sessions from owner-bound Loom capabilities."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def create_session(
        self,
        execute: Callable[[object, str | None], object],
        seed: object,
    ) -> LoomSession:
        """Bind the local capability and resolve the explicit seed once."""
        session = LoomSession(execute)
        session.resolve(seed)
        return session

    def start(
        self,
        execute: Callable[[object, str | None], object],
        seed: object,
        logo: str = "dix",
    ) -> int:
        """Resolve the seed and run VisiData without exposing provider selection."""
        from visidata import vd

        from .branding import show_logo
        from .ui import ReferenceSheet

        session = self.create_session(execute, seed)
        show_logo(logo)
        vd.options.disp_menu = False
        sheet = ReferenceSheet(session, logo=logo)
        sheet.reload()
        vd.run(sheet)
        return 0
