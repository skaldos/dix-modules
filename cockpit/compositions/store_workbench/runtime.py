from __future__ import annotations

from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext

from .session import StoreSession


class Runtime:
    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object],
                 catalog, provider, values, workspace):
        self.catalog, self.values, self.workspace = catalog, values, workspace
        catalog.require("register_provider")("roba", provider)

    def create_session(self, session: str = "dix") -> StoreSession:
        return StoreSession(self.catalog, self.values, session)

    def start(self, session: str = "dix", logo: str = "dix") -> int:
        from .ui import StoreSheet, run_store

        def opener(store_id):
            record = self.catalog.require("record")(store_id, session)
            return self.workspace.require("open_store")(
                store_id=store_id, revision=record["revision"], session=session, logo=logo)

        sheet = StoreSheet(self.create_session(session), logo=logo, opener=opener)
        sheet.reload()
        return run_store(sheet)
