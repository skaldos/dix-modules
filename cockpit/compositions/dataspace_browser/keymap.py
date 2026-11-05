"""Explicit process-local bindings for the Dataspace sheet and existing whole-value editor."""
from __future__ import annotations

from collections import OrderedDict
from importlib.metadata import version

from visidata.settings import SettingsMgr

from visidata import vd

NAV = {'h': 'go-left', 'j': 'go-down', 'k': 'go-up', 'l': 'go-right',
       'Left': 'go-left', 'Down': 'go-down', 'Up': 'go-up', 'Right': 'go-right',
       'PgUp': 'go-pageup', 'PgDn': 'go-pagedown', 'gg': 'go-top', 'G': 'go-bottom'}
BINDINGS = {**NAV, 'Enter': 'dataspace-enter', 'q': 'dataspace-parent',
            ':': 'dataspace-prompt', '^R': 'dataspace-reload', 'y': 'dataspace-copy'}
VALUE_BINDINGS = {**NAV, 'Enter': 'dataspace-value-enter', 'q': 'dataspace-value-parent',
                  'e': 'edit-toml-scalar', 'a': 'add-local-value', 'i': 'insert-local-list-value',
                  'r': 'rename-local-mapping-key', 'd': 'delete-local-value', 'y': 'copy-local-register',
                  'p': 'put-local-register-replacement', 'A': 'put-local-register-container',
                  'I': 'insert-local-register-list', 'zC': 'commit-local-definition',
                  '^S': 'commit-local-definition'}


def configure(sheet):
    message = 'Cockpit Dataspace requires the pinned VisiData 3.4 SettingsMgr and command APIs'
    registry = getattr(vd, 'bindkeys', None)
    if (version('visidata') != '3.4' or type(registry) is not SettingsMgr
            or type(registry).clear is not OrderedDict.clear):
        raise RuntimeError(message)
    editor = sheet.value_sample
    type(editor).addCommand(None, 'dataspace-value-enter',
                           'vd.push(sheet.openRow(cursorRow)) if cursorRow is not None else None',
                           'drill into a local whole-value draft', replay=False)
    type(editor).addCommand(None, 'dataspace-value-parent', 'vd.remove(sheet)',
                           'close this local view without implicitly saving', replay=False)
    for sample, bindings in [(sheet, BINDINGS), (editor, VALUE_BINDINGS)]:
        if any(sample.getCommand(command) is None for command in bindings.values()):
            raise RuntimeError(message)
    registry.clear()
    for sample, bindings in [(sheet, BINDINGS), (editor, VALUE_BINDINGS)]:
        for key, command in bindings.items():
            vd.bindkey(key, command, type(sample))
    expected = {}
    for sample, bindings in [(sheet, BINDINGS), (editor, VALUE_BINDINGS)]:
        for key, command in bindings.items():
            expected.setdefault(vd.prettykeys(key), {})[type(sample).__name__] = command
    if dict(registry) != expected:
        raise RuntimeError(message)
    vd.options.disp_menu = False
    return expected
