from __future__ import annotations

from collections.abc import Mapping

from dix.core.composition import CompositionRuntimeContext

from .draft import ValueDraft, parse_toml_literal


class Runtime:
    """Expose provider-neutral local value editing primitives."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def create_draft(self, value: object) -> ValueDraft:
        return ValueDraft(value)

    def parse_toml_literal(self, raw: str) -> object:
        return parse_toml_literal(raw)

    def create_sheet(self, draft: object, *, logo: str = "dix", title: str = "Local value",
                     on_commit: object = None) -> object:
        from .ui import CommitValueSheet

        return CommitValueSheet(draft, logo=logo, title=title, on_commit=on_commit)

    def start(self, value: object, logo: str = "dix", title: str = "TOML value") -> int:
        from visidata import vd

        from .branding import show_logo
        from .ui import ValueSheet

        draft = self.create_draft(value)
        show_logo(logo)
        vd.options.disp_menu = False
        sheet = ValueSheet(draft, logo=logo, title=title)
        sheet.reload()
        vd.run(sheet)
        return 0
