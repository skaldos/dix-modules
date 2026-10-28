"""Pinned VisiData 3.4 integration, owned only by the dedicated Store process."""
from __future__ import annotations

from collections import OrderedDict
from importlib.metadata import version

from visidata.settings import SettingsMgr

# Importing visidata completes its core, loaders, finalInit and feature imports.
from visidata import Sheet, vd

BINDINGS = {
    'h': 'go-left', 'j': 'go-down', 'k': 'go-up', 'l': 'go-right',
    'Left': 'go-left', 'Down': 'go-down', 'Up': 'go-up', 'Right': 'go-right',
    'PgUp': 'go-pageup', 'PgDn': 'go-pagedown', 'gg': 'go-top', 'G': 'go-bottom',
    'Enter': 'cockpit-store-enter', 'q': 'cockpit-store-parent',
    ':': 'cockpit-store-prompt', '^S': 'cockpit-store-save', '^R': 'cockpit-store-reload',
}


class StoreKeymapCompatibilityError(RuntimeError):
    """A fixed, credential-free startup error, never an untrusted runtime repr."""


def configure_store(sheet):
    message = 'Cockpit Store requires VisiData 3.4 with its SettingsMgr binding and command/input APIs'
    registry = getattr(vd, 'bindkeys', None)
    commands = getattr(vd, 'commands', None)
    if (version('visidata') != '3.4' or type(registry) is not SettingsMgr
            or type(commands) is not SettingsMgr
            or not isinstance(getattr(registry, 'allobjs', None), dict)
            or type(registry).clear is not OrderedDict.clear
            or any(not isinstance(k, str) or not isinstance(v, dict)
                   for k, v in vd.bindkeys.items())
            or not all(callable(getattr(obj, name, None)) for obj, name in (
                (vd, 'bindkey'), (vd, 'input'), (vd, 'editText'),
                (Sheet, 'editCell'), (Sheet, 'addCommand'), (Sheet, 'getCommand')))):
        raise StoreKeymapCompatibilityError(message)
    # Check inherited navigation and Store-specific commands before mutating the registry.
    if not isinstance(sheet, Sheet) or any(
            sheet.getCommand(command) is None for command in BINDINGS.values()):
        raise StoreKeymapCompatibilityError(message)
    before = sum(len(scopes) for scopes in vd.bindkeys.values())
    vd.bindkeys.clear()  # Complete reset of every class/global/instance binding, not a denylist.
    cleared = len(vd.bindkeys)
    try:
        for key, command in BINDINGS.items():
            vd.bindkey(key, command, type(sheet))
        expected = {vd.prettykeys(k): {type(sheet).__name__: v} for k, v in BINDINGS.items()}
        if dict(vd.bindkeys) != expected:
            raise StoreKeymapCompatibilityError(message)
    except Exception:  # noqa: BLE001 - fail closed before curses with a fixed public error
        # Never enter curses with a partial keymap. Do not silently fall back to defaults.
        raise StoreKeymapCompatibilityError(message) from None
    vd.options.disp_menu = False
    return {'version': '3.4', 'before': before, 'cleared': cleared, 'bindings': expected}
