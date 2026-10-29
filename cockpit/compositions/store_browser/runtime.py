from __future__ import annotations

from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext

from .session import BrowserSession, SelectedBrowserSession


class Runtime:
    """Bind a local catalog and one provider to independent browser sessions."""

    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object],
                 catalog, provider, values) -> None:
        self.catalog, self.values = catalog, values
        catalog.require("register_provider")("roba", provider)

    def create_session(self, session: str = "dix") -> BrowserSession:
        return BrowserSession(self.catalog, session)

    def new_store(self, session: str = "dix", logo: str = "dix") -> object:
        from visidata import vd

        providers = self.catalog.require("providers_list")()
        selected = vd.input("Provider (" + ", ".join(providers) + "): ",
                            value=providers[0] if len(providers) == 1 else "", record=False)
        draft = self.catalog.require("draft")(selected)
        return self.edit_store(draft, session=session, logo=logo)

    def edit_store(self, value: object, *, session: str = "dix", logo: str = "dix",
                   original_id: str | None = None) -> object:
        from visidata import vd

        draft = self.values.require("create_draft")(value)
        browser = self.create_session(session)

        def commit(changed):
            try:
                if original_id is None:
                    self.catalog.require("create")(changed, session)
                else:
                    self.catalog.require("update")(original_id, changed, session)
            except Exception as exc:  # noqa: BLE001 - secret-redacting UX boundary
                vd.fail(browser.safe(f"{type(exc).__name__}: {exc}", changed))
            vd.status("Store catalog committed locally; target was not contacted")

        return self.values.require("create_sheet")(
            draft, logo=logo, title="Local Store definition", on_commit=commit)

    def start(self, session: str = "dix", logo: str = "dix", side: str = "A") -> int:
        from visidata import vd

        from .ui import StoreSheet

        browser = self.create_session(session)
        sheet = StoreSheet(browser, self, logo=logo, side=side)
        sheet.reload()
        vd.options.disp_menu = False
        vd.run(sheet)
        return 0


    def create_selected_session(self, store_id: str, session: str = "dix") -> BrowserSession:
        return SelectedBrowserSession(self.catalog, session, store_id)

    def start_selected(self, store_id: str, session: str = "dix", logo: str = "dix") -> int:
        from visidata import vd

        from .ui import ReadOnlyStoreSheet

        browser = self.create_selected_session(store_id, session)
        sheet = ReadOnlyStoreSheet(browser, logo=logo)
        sheet.reload()
        vd.options.disp_menu = False
        vd.run(sheet)
        return 0
