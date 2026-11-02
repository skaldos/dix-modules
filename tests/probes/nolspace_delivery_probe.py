"""Exercise external Nolspace roots with either source or wheel DIX/ROBA, no Cockpit/VD."""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import dix
import roba
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path
from roba import RobaClient, create_context, start_daemon, stop_daemon

modules_root, mode = Path(sys.argv[1]), sys.argv[2]
if mode == 'wheel':
    for package in (dix, roba):
        assert 'site-packages' in str(package.__file__)
for name in ('visidata', '_curses'):
    assert name not in sys.modules
root = Path(tempfile.mkdtemp(prefix='nd69-', dir='/tmp'))
env = {'ROBA_RUNTIME_ROOT': str(root / 'r'), 'ROBA_LOGS_ROOT': str(root / 'l')}
registry = create_core_component_registry()
mods = registry.require('module', ModuleComponent)
comps = registry.require('composition', CompositionComponent)
loaded, instances = [], []
daemon = None


def create(use):
    ident = str(len(instances))
    item = comps.create_instance(CompositionInstanceSpec(ident, use, {}, modules_root),
                                 owner_scope_id='delivery')
    instances.append(ident)
    return item.api


try:
    for name in ('dix/state', 'dix/cli', 'dix/norn', 'dix/roba'):
        mods.load_module(first_party_module_path(name), module_id=name); loaded.append(name)
    for name in ('core', 'roba'):
        ident = 'skaldos/stores/nolspace/' + name
        mods.load_module(modules_root / 'stores/nolspace' / name, module_id=ident); loaded.append(ident)
    api = create('skaldos/stores/nolspace/core/api')
    provider = create('skaldos/stores/nolspace/roba/provider')
    connection = create('skaldos/stores/nolspace/roba/connection')
    daemon = start_daemon('delivery', env=env)
    context = create_context(context_id='data', control=str(daemon.control_locator),
                             control_token=daemon.control_token, env=env)
    owner = RobaClient(env={}).context(locator=str(context.direct_locator), token=context.owner_token)
    owner.set('same', 'context')
    owner.instance_create(instance_id='same', state={'same': 'instance'})
    root_view = connection.require('root')({'context_id': 'data', 'context_locator': str(context.direct_locator),
                                           'token': context.owner_token, 'timeout': 2.0})
    assert api.require('enumerate')(provider, root_view) == [{'name': 'values'}, {'name': 'instances'}]
    values = api.require('lookup')(provider, root_view, 'values')
    assert api.require('enumerate')(provider, values) == [{'name': 'same'}]
    assert api.require('lookup')(provider, values, 'same')['value'] == 'context'
    api.require('upsert')(provider, values, {'name': 'new', 'type': 'null', 'value': None})
    assert owner.get('new') is None
    assert api.require('delete')(provider, values, 'new') == {'name': 'new'}
    child = api.require('lookup')(provider, root_view, 'instances')
    assert api.require('enumerate')(provider, child) == [{'name': 'same'}]
    instance = api.require('lookup')(provider, child, 'same')
    assert api.require('lookup')(provider, instance, 'same')['value'] == 'instance'
    for view, target in ((values, owner), (instance, owner.with_scope('id:same'))):
        for kind, value in [('array', [7, {'enabled': False}]),
                            ('object', {'items': [1, None, {'leaf': 'whole-root'}]})]:
            item = {'name': 'complex', 'type': kind, 'value': value}
            assert api.require('upsert')(provider, view, item) == item
            assert target.get('complex') == value
    print(mode, 'whole standard array/object replacements in Context and Instance: OK')
    print(mode, 'external core/provider, unchanged Norn boundaries, native keys/metadata, explicit lookup/upsert/delete: OK')
finally:
    if daemon is not None:
        stop_daemon(daemon='id:delivery', env=env)
    for ident in reversed(instances): comps.destroy_instance('delivery', ident)
    for name in reversed(loaded): mods.unload_module(name)
    shutil.rmtree(root)
