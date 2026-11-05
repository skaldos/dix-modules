from __future__ import annotations

from .session import DataspaceSession


class Runtime:
    """UI adapter over a caller-owned handle, not a materializer or a storage client."""

    def __init__(self, *, context, config, values):
        self.values = values

    def create_session(self, space: object, guard: object = None, title: str = 'Dataspace') -> object:
        return DataspaceSession(space, guard=guard, title=title)

    def start(self, space: object, guard: object = None, title: str = 'Dataspace',
              logo: str = 'dix') -> int:
        from visidata import vd

        from .keymap import configure
        from .ui import DataspaceSheet

        browser = self.create_session(space, guard, title)
        sheet = DataspaceSheet(browser, self.values, logo=logo)
        sheet.reload()
        configure(sheet)
        vd.options.disp_menu = False
        vd.run(sheet)
        return 0
