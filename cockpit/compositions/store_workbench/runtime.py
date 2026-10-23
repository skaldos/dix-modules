from __future__ import annotations

from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext

from .session import StoreSession


class Runtime:
    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object],
                 catalog, provider, values):
        self.catalog, self.values = catalog, values
        catalog.require("register_provider")("roba", provider)

    def create_session(self, session: str = "dix") -> StoreSession:
        return StoreSession(self.catalog, self.values, session)

    def start(self, session: str = "dix", logo: str = "dix") -> int:
        from visidata import vd

        from .ui import StoreSheet

        sheet = StoreSheet(self.create_session(session), logo=logo)
        sheet.reload()
        vd.run(sheet)
        return 0
