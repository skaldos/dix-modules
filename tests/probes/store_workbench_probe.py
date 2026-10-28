"""Test-only real-terminal observer; not installed and not a second Store provider."""
from __future__ import annotations

import copy
import importlib
import json
import os
import socket
import sys
from pathlib import Path

from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

root, evidence, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
registry = create_core_component_registry()
modules = registry.require('module', ModuleComponent)
component = registry.require('composition', CompositionComponent)
for name in ('state', 'cli', 'norn', 'roba'):
    modules.load_module(first_party_module_path('dix/' + name), module_id='dix/' + name)
for name in ('visidata', 'cockpit'):
    modules.load_module(root / name, module_id='skaldos/' + name)
instance = component.create_instance(CompositionInstanceSpec(
    'probe', 'skaldos/cockpit/store_workbench', {}, root), owner_scope_id='probe')
controller = instance.api.require('create_session')('a')
ui = importlib.import_module(instance.runtime.__class__.__module__ + '.ui')
metrics = {'create': 0, 'update': 0, 'success': 0, 'target_transport': 0}
original_connect = socket.socket.connect


def connect(sock, address):
    # Catalog transport is allowed; even an attempted external target call fails this probe.
    if not isinstance(address, str) or not address.startswith(os.environ['DIX_COCKPIT_RUNTIME_ROOT'] + '/'):
        metrics['target_transport'] += 1
        raise AssertionError('external target transport is forbidden')
    return original_connect(sock, address)


socket.socket.connect = connect


class Api:
    def __init__(self, **funcs):
        self.funcs = funcs

    def require(self, name):
        return self.funcs[name]


if mode == 'types':
    rows = {}

    def create(value, session):
        if value['store_id'] in ('', 'invalid-new') or value['connection']['timeout'] <= 0:
            raise ValueError('test validation failure')
        rows[value['store_id']] = copy.deepcopy(value)

    def update(ident, value, session):
        create(value, session)
        if ident != value['store_id']:
            del rows[ident]

    controller.catalog = Api(
        providers_list=lambda: ['fixture'],
        draft=lambda provider: {'store_id': '', 'provider': 'fixture', 'connection': {
            'text': 'initial', 'count': 1, 'timeout': 5.0, 'enabled': True, 'nested': list(range(80))}},
        list=lambda session: list(copy.deepcopy(rows).values()),
        get=lambda ident, session: copy.deepcopy(rows[ident]), create=create, update=update)

catalog = controller.catalog
funcs = {name: catalog.require(name) for name in
         ('providers_list', 'draft', 'list', 'get', 'create', 'update')}
for name in ('create', 'update'):
    original = funcs[name]

    def counted(*args, _name=name, _call=original):
        metrics[_name] += 1
        result = _call(*args)
        metrics['success'] += 1
        return result

    funcs[name] = counted
controller.catalog = Api(**funcs)


def observe(sheet, editing=False):
    value = {'path': list(controller.path), 'dirty': controller.dirty,
             'draft': controller.draft.at() if controller.draft else None,
             'baseline': controller.baseline, 'error': controller.error,
             'entries': controller.entries, 'metrics': metrics, 'editing': editing,
             'exit': sheet.exiting, 'cursor': [sheet.cursorRowIndex, sheet.cursorVisibleColIndex],
             'registry': getattr(sheet, 'keymap_proof', None),
             'columns': [c.name for c in sheet.columns],
             'menu': bool(ui.vd.options.disp_menu), 'prompt': getattr(sheet, 'in_prompt', False)}
    # Only synthetic draft credentials can appear in this probe, never acquired owner caps.
    temporary = evidence.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(evidence)


class ObservedSheet(ui.StoreSheet):
    def execCommand(self, *args, **kwargs):
        try:
            return super().execCommand(*args, **kwargs)
        finally:
            observe(self)

    def promptStore(self):
        self.in_prompt = True
        observe(self)
        try:
            return super().promptStore()
        finally:
            self.in_prompt = False
            observe(self)

    def reload(self):
        super().reload()
        observe(self)

    def editCell(self, **kwargs):
        observe(self, editing=True)
        try:
            return super().editCell(**kwargs)
        finally:
            observe(self)

    def _status_error(self):
        super()._status_error()
        observe(self)


ui.Sheet.addCommand('F12', 'up067-future-default', 'sheet.session.error = \"future default ran\"', 'test-only injected default')
sheet = ObservedSheet(controller)
sheet.reload()
try:
    ui.run_store(sheet)
finally:
    observe(sheet)
    component.destroy_instance('probe', 'probe')
    for name in ('skaldos/cockpit', 'skaldos/visidata', 'dix/roba', 'dix/norn', 'dix/cli', 'dix/state'):
        modules.unload_module(name)
