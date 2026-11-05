from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


def bind(catalog, api, calls=None):
    calls = [] if calls is None else calls

    def validate(value):
        calls.append('validate')
        if set(value) != {'target'} or type(value['target']) is not str:
            raise ValueError('opaque credential value must not appear in errors')
        return value

    def materialize(value):
        calls.append('materialize')
        raise AssertionError('Catalog must never materialize')

    catalog.require('register_materializer')('reference', api(
        draft=lambda: {'target': ''}, validate=validate, materialize=materialize))
    return calls


def entry(ident='private'):
    return {'dataspace_id': ident, 'materializer': 'reference',
            'configuration': {'target': 'opaque-sensitive-target'}}


def test_native_catalog_is_separate_detached_revisioned_and_target_free(store_graph, api):
    create, runtime, root = store_graph
    store = create('skaldos/cockpit/store_catalog').api
    assert store.require('list')('a') == []
    catalog = create('skaldos/cockpit/dataspace_catalog').api
    calls = bind(catalog, api)
    assert catalog.require('materializers_list')() == ['reference']
    assert catalog.require('list')('a') == []
    assert catalog.require('draft')('reference') == {
        'dataspace_id': '', 'materializer': 'reference', 'configuration': {'target': ''}}
    value = entry()
    catalog.require('create')(value, 'a')
    original = catalog.require('record')('private', 'a')
    assert set(original) == {'definition', 'revision'} and len(original['revision']) == 32
    value['configuration']['target'] = 'mutated-input'
    original['definition']['configuration']['target'] = 'mutated-return'
    assert catalog.require('get')('private', 'a') == entry()
    old = catalog.require('record')('private', 'a')
    catalog.require('update')('private', entry(), 'a')
    newer = catalog.require('record')('private', 'a')
    assert newer['revision'] != old['revision']
    catalog.require('update')('private', entry('evia'), 'a')
    assert catalog.require('list')('a') == [entry('evia')]
    with pytest.raises(ValueError):
        catalog.require('record')('private', 'a')
    other = create('skaldos/cockpit/dataspace_catalog').api
    # A catalog read uses no materializer code and needs no domain binding in this other graph.
    assert other.require('get')('evia', 'a') == entry('evia')
    catalog.require('remove')('evia', 'a')
    assert catalog.require('list')('a') == []
    assert store.require('list')('a') == []
    assert 'materialize' not in calls
    assert set((root / 'r/sessions/a').iterdir()) == {
        root / 'r/sessions/a/roba', root / 'r/sessions/a/owner.json',
        root / 'r/sessions/a/stores.lock', root / 'r/sessions/a/dataspaces.lock'}
    runtime.require('start')(session='b')
    assert catalog.require('list')('b') == []
    catalog.require('create')(entry(), 'a')
    runtime.require('stop')(session='a')
    runtime.require('start')(session='a')
    assert catalog.require('list')('a') == []


def test_native_concurrent_catalog_updates_and_duplicate_rename(store_graph, api):
    create, _, _ = store_graph
    catalogs = [create('skaldos/cockpit/dataspace_catalog').api for _ in range(4)]
    for catalog in catalogs:
        bind(catalog, api)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: catalogs[i].require('create')(entry(str(i)), 'a'), range(4)))
    assert [item['dataspace_id'] for item in catalogs[0].require('list')('a')] == ['0', '1', '2', '3']
    before = catalogs[0].require('record')('0', 'a')
    with pytest.raises(ValueError, match='already exists'):
        catalogs[0].require('update')('0', entry('1'), 'a')
    assert catalogs[0].require('record')('0', 'a') == before


@pytest.mark.parametrize('change', [
    {'dataspace_id': ''}, {'dataspace_id': 'line\nbreak'}, {'materializer': 'unbound.module'},
    {'configuration': []}, {'configuration': {'target': object()}},
    {'configuration': {'target': float('nan')}}, {'configuration': {'wrong': 'do not leak'}},
    {'configuration': {'target': ('not', 'native')}}, {'extra': True},
])
def test_invalid_catalog_requests_do_not_change_saved_revision(store_graph, api, change):
    create, _, _ = store_graph
    catalog = create('skaldos/cockpit/dataspace_catalog').api
    calls = bind(catalog, api)
    catalog.require('create')(entry(), 'a')
    before = catalog.require('record')('private', 'a')
    with pytest.raises(ValueError) as caught:
        catalog.require('update')('private', {**entry(), **change}, 'a')
    assert 'do not leak' not in str(caught.value)
    assert catalog.require('record')('private', 'a') == before
    assert 'materialize' not in calls


@pytest.mark.parametrize('record', [None, {}, {'definition': entry(), 'revision': 'bad'},
    {'definition': entry('wrong-id'), 'revision': 'a' * 32},
    {'definition': {**entry(), 'configuration': {'x': float('inf')}}, 'revision': 'a' * 32}])
def test_malformed_private_records_never_repair_or_write(store_graph, api, monkeypatch, record):
    create, _, _ = store_graph
    bound = create('skaldos/cockpit/dataspace_catalog')
    bind(bound.api, api)
    writes = []

    @contextmanager
    def corrupt(_session):
        yield SimpleNamespace(get=lambda _key: {'private': record},
                              set=lambda *args: writes.append(args))

    monkeypatch.setattr(bound.runtime, '_catalog', corrupt)
    for op, args in [('list', ('a',)), ('get', ('private', 'a')),
                     ('update', ('private', entry(), 'a')), ('remove', ('private', 'a'))]:
        with pytest.raises(RuntimeError, match='invalid shape'):
            bound.api.require(op)(*args)
    assert writes == []


def test_materializers_are_complete_local_sync_capabilities_not_code_strings(load_runtime, api):
    runtime = load_runtime('cockpit/compositions/dataspace_materializers/runtime.py')
    a, b = runtime(context=None, config={}), runtime(context=None, config={})
    calls = []
    capability = api(draft=lambda: {'target': 'x'}, validate=lambda value: value,
                     materialize=lambda value: calls.append(value))
    a.register('one', capability)
    assert a.list() == ['one'] and b.list() == []
    for other in ('unbound', 'os.system', '../../code'):
        with pytest.raises(ValueError, match='unknown'):
            b.validate(other, {})
    with pytest.raises(ValueError, match='already'):
        a.register('one', capability)
    with pytest.raises(ValueError, match='requires'):
        b.register('bad', api(draft=dict, validate=dict))
    async def async_draft():
        return {}
    with pytest.raises(ValueError, match='synchronous'):
        b.register('async', api(draft=async_draft, validate=dict, materialize=dict))
    value = a.draft('one'); value['target'] = 'changed'
    assert a.draft('one') == {'target': 'x'}
    assert a.validate('one', {'target': 'x'}) == {'target': 'x'}
    assert calls == []


def test_owned_materialization_returns_handle_without_copying_and_closes_invalid_handle(load_runtime, api):
    runtime = load_runtime('cockpit/compositions/dataspace_materializers/runtime.py')(context=None, config={})
    closed, materialized = [], []
    space = SimpleNamespace(describe=dict, get=lambda *a: None,
                            set=lambda *a: None, delete=lambda *a: None)
    lease = SimpleNamespace(space=space, close=lambda: closed.append(True))
    def materialize(value):
        materialized.append(copy.deepcopy(value))
        return lease
    runtime.register('bound', api(draft=dict, validate=lambda value: value, materialize=materialize))
    assert runtime.materialize('bound', {'x': 1}) is lease
    assert materialized == [{'x': 1}] and closed == []
    lease.space = object()
    with pytest.raises(TypeError, match='owned'):
        runtime.materialize('bound', {'x': 1})
    assert closed == [True]


def test_lost_owner_refuses_before_any_path_or_catalog_access(load_runtime, api):
    touched = []
    def lost(**kwargs):
        raise PermissionError('owner no longer exists')
    runtime = load_runtime('cockpit/compositions/dataspace_catalog/runtime.py')(
        context=None, config={}, runtime=api(owner_environment=lost, paths=lambda **kw: touched.append(kw)),
        contexts=api(), materializers=api())
    with pytest.raises(PermissionError, match='owner'):
        runtime.list('a')
    assert touched == []


def test_actual_loader_owns_independent_materializer_bindings_and_unloads(api, tmp_path):
    import sys
    from pathlib import Path

    from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
    from dix.core.composition import CompositionInstanceSpec
    from dix.modules import first_party_module_path

    before = set(sys.modules)
    registry = create_core_component_registry()
    modules = registry.require('module', ModuleComponent)
    compositions = registry.require('composition', CompositionComponent)
    loaded, instances = [], []
    try:
        for name in ('dix/state', 'dix/cli', 'dix/norn', 'dix/roba'):
            modules.load_module(first_party_module_path(name), module_id=name)
            loaded.append(name)
        root = Path(__file__).parents[1]
        for name, relative in [('skaldos/stores/nolspace/core', 'stores/nolspace/core'),
                               ('skaldos/stores/nolspace/roba', 'stores/nolspace/roba'),
                               ('skaldos/visidata', 'visidata'), ('skaldos/cockpit', 'cockpit')]:
            modules.load_module(root / relative, module_id=name)
            loaded.append(name)
        for ident in ('first', 'second'):
            bound = compositions.create_instance(CompositionInstanceSpec(
                ident, 'skaldos/cockpit/dataspace_catalog', {}, tmp_path), owner_scope_id='catalog')
            instances.append(ident)
            if ident == 'first':
                bind(bound.api, api)
                assert bound.api.require('materializers_list')() == ['reference']
            else:
                assert bound.api.require('materializers_list')() == []
                with pytest.raises(ValueError, match='unknown'):
                    bound.api.require('draft')('reference')
    finally:
        for ident in reversed(instances):
            compositions.destroy_instance('catalog', ident)
        for name in reversed(loaded):
            modules.unload_module(name)
    assert not any(name.startswith(('_dix_composition_', '_dix_application_'))
                   for name in set(sys.modules) - before)
