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
