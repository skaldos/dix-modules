from __future__ import annotations

import copy
from contextlib import contextmanager
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def preserve_process_keymap():
    # The dedicated process owns its blank keymap; test processes must restore their caller.
    from visidata import vd

    bindings = copy.deepcopy(dict(vd.bindkeys))
    menu = vd.options.disp_menu
    yield
    vd.bindkeys.clear()
    vd.bindkeys.update(bindings)
    vd.options.disp_menu = menu


class CountingSpace:
    def __init__(self):
        self.calls = []
        self.values = {'session': {}, 'project': {'root': '/private'}}
        self.fail = None

    def describe(self):
        self.calls.append(('describe',))
        def field(contract, ops, default=False):
            return {'contract': contract, 'operations': list(ops), 'effective_operations': list(ops),
                    'has_default': default}
        return {'id': 'runtime', 'sets': {
            'session': {'id': 'session', 'mounted': True, 'fields': {
                'cwd': field('any', ['get', 'set', 'delete']),
                'timeout': field('number', ['get', 'set'], True)}},
            'project': {'id': 'project', 'mounted': True, 'fields': {
                'root': field('path', ['get']), 'color': field('color', ['get', 'set'])}}}}

    def get(self, role, field):
        self.calls.append(('get', role, field))
        if self.fail:
            raise self.fail
        if (role, field) == ('session', 'timeout') and field not in self.values[role]:
            return 5.0
        return copy.deepcopy(self.values[role][field])

    def set(self, role, field, value):
        self.calls.append(('set', role, field, copy.deepcopy(value)))
        if self.fail:
            raise self.fail
        if (role, field) == ('project', 'color'):
            if type(value) is not str or not value.startswith('#'):
                raise ValueError('invalid color with secret payload')
            value = value.lower()
        self.values[role][field] = copy.deepcopy(value)
        return copy.deepcopy(value)

    def delete(self, role, field):
        self.calls.append(('delete', role, field))
        if self.fail:
            raise self.fail
        del self.values[role][field]
        return {'set': role, 'field': field}


@pytest.fixture
def controller(load_runtime):
    # The controller file has no provider, SDK, VisiData or sibling-package imports.
    path = Path(__file__).parents[1] / 'cockpit/compositions/dataspace_browser/session.py'
    import importlib.util
    spec = importlib.util.spec_from_file_location('dataspace_session_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    space = CountingSpace()
    return module.DataspaceSession(space), space


def test_structure_and_navigation_are_describe_only_and_detached(controller):
    browser, space = controller
    assert space.calls == []
    assert browser.reload()
    assert browser.rows() == [{'key': 'runtime', 'kind': 'layout'}]
    browser.enter('runtime')
    assert [r['key'] for r in browser.rows()] == ['session', 'project']
    browser.enter('session')
    rows = browser.rows()
    assert all('value' not in r and not r['loaded'] for r in rows)
    assert rows[1]['has_default'] and rows[1]['effective_operations'] == ['get', 'set']
    rows[0]['operations'].clear()
    assert browser.rows()[0]['operations'] == ['get', 'set', 'delete']
    browser.parent(); browser.parent()
    assert browser.reload()
    assert space.calls == [('describe',), ('describe',)]
    assert space.values['session'] == {}


def test_explicit_get_default_set_canonical_return_and_delete_have_exact_calls(controller):
    browser, space = controller
    browser.reload(); space.calls.clear()
    assert browser.load('session', 'timeout')
    assert browser.cache[('session', 'timeout')] == 5.0
    assert space.values['session'] == {}
    assert 'proof of storage' in browser.notice
    assert browser.set_value('project', 'color', '#AABBCC')
    assert browser.cache[('project', 'color')] == '#aabbcc'
    assert browser.set_value('session', 'cwd', {'nested': [1, None]})
    assert browser.delete_value('session', 'cwd')
    assert ('session', 'cwd') not in browser.cache
    assert space.calls == [('get', 'session', 'timeout'),
        ('set', 'project', 'color', '#AABBCC'), ('set', 'session', 'cwd', {'nested': [1, None]}),
        ('delete', 'session', 'cwd')]


@pytest.mark.parametrize('value', ['plain', 3, 2.5, True, None, [1, {'x': None}], {'x': [True]}])
def test_whole_values_do_not_preread_or_mutate_caller_values(controller, value):
    browser, space = controller
    browser.reload(); space.calls.clear()
    original = copy.deepcopy(value)
    assert browser.set_value('session', 'cwd', value)
    assert len(space.calls) == 1 and space.calls[0] == ('set', 'session', 'cwd', original)
    assert browser.cache[('session', 'cwd')] == original and type(browser.cache[('session', 'cwd')]) is type(value)
    if type(value) in (list, dict):
        value.clear()
        assert browser.cache[('session', 'cwd')] == original


def test_local_read_only_and_effective_caps_refuse_before_handle_effect(controller):
    browser, space = controller
    browser.reload(); space.calls.clear()
    assert not browser.set_value('project', 'root', 'forbidden')
    assert not browser.delete_value('project', 'root')
    browser.description['sets']['session']['fields']['cwd']['effective_operations'] = []
    assert not browser.load('session', 'cwd')
    assert not browser.set_value('session', 'cwd', 'forbidden')
    assert space.calls == [] and 'PermissionError' in browser.error


def test_stale_revision_barrier_prevents_every_effect(controller):
    browser, space = controller
    browser.reload(); space.calls.clear()
    @contextmanager
    def stale():
        raise RuntimeError('stale secret configuration must not appear')
        yield
    browser.guard = stale
    assert not browser.load('session', 'timeout')
    assert not browser.set_value('session', 'cwd', 'blocked')
    assert not browser.delete_value('session', 'cwd')
    assert not browser.reload()
    assert space.calls == []
    assert 'secret' not in browser.error and 'RuntimeError' in browser.error


@pytest.mark.parametrize('error', [KeyError('missing'), PermissionError('secret'),
    TimeoutError('opaque configuration'), RuntimeError('provider secret'), ValueError('contract secret')])
def test_errors_are_visible_do_not_replace_cache_or_invent_defaults(controller, error):
    browser, space = controller
    browser.reload()
    assert browser.load('session', 'timeout')
    previous = copy.deepcopy(browser.cache)
    space.fail = error
    assert not browser.load('session', 'timeout')
    assert not browser.set_value('session', 'cwd', 'x')
    assert browser.cache == previous
    assert type(error).__name__ in browser.error
    assert 'may have changed' in browser.notice
    assert 'secret' not in browser.error and 'opaque' not in browser.error


def test_post_write_output_failure_never_claims_rollback(controller):
    browser, space = controller
    browser.reload()
    def write_then_fail(role, field, value):
        space.values[role][field] = value
        raise ValueError('output contract rejected secret')
    space.set = write_then_fail
    assert not browser.set_value('session', 'cwd', 'written')
    assert space.values['session']['cwd'] == 'written'
    assert 'may have changed' in browser.notice
    assert ('session', 'cwd') not in browser.cache


@pytest.fixture
def browser_runtime(tmp_path):
    from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
    from dix.core.composition import CompositionInstanceSpec
    from dix.modules import first_party_module_path
    registry = create_core_component_registry()
    modules = registry.require('module', ModuleComponent)
    compositions = registry.require('composition', CompositionComponent)
    loaded = []
    root = Path(__file__).parents[1]
    try:
        for name in ('dix/state', 'dix/cli', 'dix/norn', 'dix/roba'):
            modules.load_module(first_party_module_path(name), module_id=name); loaded.append(name)
        for name, relative in [('skaldos/stores/nolspace/core', 'stores/nolspace/core'),
                               ('skaldos/stores/nolspace/roba', 'stores/nolspace/roba'),
                               ('skaldos/visidata', 'visidata'), ('skaldos/cockpit', 'cockpit')]:
            modules.load_module(root / relative, module_id=name); loaded.append(name)
        bound = compositions.create_instance(CompositionInstanceSpec(
            'browser', 'skaldos/cockpit/dataspace_browser', {}, tmp_path), owner_scope_id='browser-test')
        yield bound
    finally:
        compositions.destroy_instance('browser-test', 'browser')
        for name in reversed(loaded):
            modules.unload_module(name)


def test_real_shared_editor_and_blank_keymap_preserve_lazy_handle_boundary(browser_runtime, monkeypatch):
    import importlib

    from visidata import vd
    ui = importlib.import_module(browser_runtime.runtime.__class__.__module__ + '.ui')
    keymap = importlib.import_module(browser_runtime.runtime.__class__.__module__ + '.keymap')
    space = CountingSpace()
    browser = browser_runtime.api.require('create_session')(space)
    sheet = ui.DataspaceSheet(browser, browser_runtime.runtime.values)
    sheet.reload()
    assert space.calls == [('describe',)]
    proof = keymap.configure(sheet)
    assert proof == dict(vd.bindkeys) and len(proof) > 12
    sheet.enter(); sheet.enter()  # Layout -> session fields; still no Get.
    assert space.calls == [('describe',)]
    assert {col.name for col in sheet.columns} >= {'operations', 'effective', 'default', 'value'}
    sheet.enter()  # Explicit lazy get of missing cwd is a visible KeyError, not an empty success.
    assert space.calls == [('describe',), ('get', 'session', 'cwd')]
    assert 'KeyError' in browser.error
    # A set on an unloaded Field asks only for type/value and never reads first.
    answers = iter(['string'])
    monkeypatch.setattr(vd, 'input', lambda *a, **kw: next(answers))
    monkeypatch.setattr(sheet, 'editCell', lambda **kw: 'written-directly')
    sheet.dispatch('s')
    assert space.calls[-1] == ('set', 'session', 'cwd', 'written-directly')
    assert browser.error == ''
    before = list(space.calls)
    from visidata import EscapeException
    def cancel(**kw):
        raise EscapeException()
    monkeypatch.setattr(sheet, 'editCell', cancel)
    sheet.dispatch('s')
    assert space.calls == before


def test_complex_editor_commits_only_the_whole_field_once(browser_runtime, monkeypatch):
    import importlib

    from visidata import vd
    ui = importlib.import_module(browser_runtime.runtime.__class__.__module__ + '.ui')
    space = CountingSpace()
    browser = browser_runtime.api.require('create_session')(space)
    sheet = ui.DataspaceSheet(browser, browser_runtime.runtime.values)
    sheet.reload(); sheet.enter(); sheet.enter()
    pushed = []
    monkeypatch.setattr(vd, 'push', lambda value: pushed.append(value))
    monkeypatch.setattr(vd, 'input', lambda *a, **kw: 'object')
    sheet.dispatch('s')
    assert space.calls == [('describe',)] and len(pushed) == 1
    editor = pushed[0]
    editor.draft.add_mapping((), 'nested', [1, {'x': None}])
    # Editing/drilling local structure has no Field effects until explicit commit.
    assert space.calls == [('describe',)]
    editor.on_commit(editor.draft.at())
    assert space.calls == [('describe',), ('set', 'session', 'cwd', {'nested': [1, {'x': None}]})]
    assert browser.cache[('session', 'cwd')] == {'nested': [1, {'x': None}]}
