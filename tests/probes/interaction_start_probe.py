"""Test-only observer around installed entrypoints, never a productive launcher."""
from __future__ import annotations

import importlib.metadata
import json
import runpy
import sys
from pathlib import Path

from visidata import vd

mode, target, evidence = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
before = {k: dict(v) for k, v in vd.bindkeys.items()}
original_run = vd.run


def observe_run(sheet):
    evidence.write_text(json.dumps({'before': before,
        'after': {k: dict(v) for k, v in vd.bindkeys.items()},
        'defaults': {k: sheet.getCommand(vd.prettykeys(k)).longname for k in ('i', '-', '^F')}}))
    return original_run(sheet)


if mode.startswith('bad-'):
    def forbidden_curses(*args, **kwargs):
        raise AssertionError('UNEXPECTED_CURSES')

    vd.initCurses = forbidden_curses
    if mode == 'bad-version':
        original_version = importlib.metadata.version
        importlib.metadata.version = lambda name: ('0.incompatible' if name == 'visidata'
                                                   else original_version(name))
    else:
        vd.bindkeys = {}
    sys.argv = [str(target), '--session', 'a']
    runpy.run_path(str(target), run_name='__main__')
else:
    vd.run = observe_run
    if mode == 'toml':
        sys.argv = [str(target), '--file', sys.argv[4]]
        runpy.run_path(str(target), run_name='__main__')
    else:
        from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
        from dix.core.composition import CompositionInstanceSpec
        from dix.modules import first_party_module_path

        registry = create_core_component_registry()
        modules = registry.require('module', ModuleComponent)
        comp = registry.require('composition', CompositionComponent)
        for name in ('state', 'cli', 'norn', 'roba'):
            modules.load_module(first_party_module_path('dix/' + name), module_id='dix/' + name)
        modules.load_module(target, module_id='skaldos/visidata')
        instance = comp.create_instance(CompositionInstanceSpec(
            'generic', 'skaldos/visidata/loom_workbench', {}, target), owner_scope_id='probe')
        try:
            instance.api.require('start')(
                lambda value, object_id=None: [{'object_id': 'demo', 'description': 'generic',
                                               'value': {'text': 'unchanged'}}], {})
        finally:
            comp.destroy_instance('probe', 'generic')
            for name in ('skaldos/visidata', 'dix/roba', 'dix/norn', 'dix/cli', 'dix/state'):
                modules.unload_module(name)
