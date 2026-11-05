from __future__ import annotations

import copy
import shutil
from dataclasses import FrozenInstanceError

import pytest
from dix.core.composition import CompositionComponentError

from tests._support.dataspace import ROOT, DataspaceGraph

CAPS = ['enumerate', 'lookup', 'upsert', 'delete']


def view(pool, caps=None):
    return {'name': pool, 'type': 'nolspace', 'value': {
        'caps': list(CAPS if caps is None else caps),
        'target': {'pool': pool, 'token': 'private-target-marker'}}}


def mounts(session=None, project=None):
    return [{'set': 'session', 'provider_alias': 'backend', 'nolspace_view': session or view('shared')},
            {'set': 'project', 'provider_alias': 'backend', 'nolspace_view': project or view('private')}]


@pytest.fixture
def fake():
    with DataspaceGraph() as graph:
        owner = graph.create('local/dataspace/fake')
        yield owner, owner.backend(), owner.materialize(mounts())


@pytest.fixture
def sources(tmp_path):
    path = tmp_path / 'fixture'
    shutil.copytree(ROOT / 'tests/fixtures/dataspace', path)
    return path


def replace(sources, file, old, new):
    path = sources / 'compositions' / file
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def test_exact_consumer_surface_describe_and_missing_default_are_detached_without_writes(fake):
    owner, backend, space = fake
    assert {name for name in dir(space) if not name.startswith('_')} == {'describe', 'get', 'set', 'delete'}
    assert backend.calls() == []
    desc = space.describe()
    assert '5.0' not in str(desc) and 'private-target-marker' not in str(desc)
    assert not {'value', 'target', 'token', 'default'} & set(str(desc).split())
    assert desc['sets']['session']['fields']['timeout']['has_default'] is True
    desc['sets']['session']['fields']['timeout']['operations'].clear()
    assert space.describe()['sets']['session']['fields']['timeout']['operations'] == ['get', 'set']
    assert backend.calls() == []
    for _ in range(3):
        assert space.get('session', 'timeout') == 5.0
    assert backend.calls() == [('lookup', 'shared', 'timeout')] * 3
    assert backend.values('shared') == {}
    assert owner.contract_calls('number') == [('input', 5.0), ('output', 5.0)]
    with pytest.raises(FrozenInstanceError):
        space._layout = None


def test_get_set_delete_each_have_one_effect_and_use_provider_canonical_return(fake):
    _, backend, space = fake
    backend.configure('shared', {'canonical': 8.0})
    assert space.set('session', 'timeout', 7.0) == 8.0
    assert backend.values('shared') == {'timeout': 7.0}
    assert backend.calls() == [('upsert', 'shared', 'timeout')]
    backend.configure('shared', {})
    assert space.get('session', 'timeout') == 7.0
    assert space.set('session', 'cwd', '/tmp/work') == '/tmp/work'
    marker = space.delete('session', 'cwd')
    assert marker == {'set': 'session', 'field': 'cwd'}
    marker['set'] = 'changed'
    assert backend.calls()[-3:] == [('lookup', 'shared', 'timeout'),
                                   ('upsert', 'shared', 'cwd'), ('delete', 'shared', 'cwd')]
    assert 'cwd' not in backend.values('shared')
    with pytest.raises(backend.missing_type()):
        space.get('session', 'cwd')
    assert backend.calls()[-1] == ('lookup', 'shared', 'cwd')


def test_input_error_is_before_write_and_output_error_after_write_is_not_rollback(fake):
    _, backend, space = fake
    with pytest.raises(ValueError, match='Invalid test color'):
        space.set('project', 'color', 'not-a-color')
    assert backend.calls() == [] and backend.values('private') == {}
    backend.configure('private', {'canonical': 'invalid-return'})
    with pytest.raises(ValueError, match='Invalid test color'):
        space.set('project', 'color', '#AABBCC')
    assert backend.calls() == [('upsert', 'private', 'color')]
    assert backend.values('private') == {'color': '#aabbcc'}
    # Canonical return was not guessed from the submitted value, and no rollback/read was added.
    assert space.get('project', 'color') == '#aabbcc'
    assert backend.calls()[-1] == ('lookup', 'private', 'color')


def test_norn_output_error_is_preserved_on_native_lookup(fake):
    _, backend, space = fake
    backend.configure('shared', {'seed': {'timeout': 'native-but-wrong-contract'}})
    with pytest.raises(ValueError) as caught:
        space.get('session', 'timeout')
    assert type(caught.value).__name__ == 'StrandOutputValueError'
    assert backend.calls() == [('lookup', 'shared', 'timeout')]


@pytest.mark.parametrize('error', [PermissionError('auth or capability'), TimeoutError('late'),
    OSError('transport'), ValueError('parse'), RuntimeError('provider')])
def test_only_stable_missing_activates_default_other_errors_are_identical(fake, error):
    _, backend, space = fake
    backend.configure('shared', {'error': error})
    with pytest.raises(type(error)) as caught:
        space.get('session', 'timeout')
    assert caught.value is error
    assert backend.calls() == [('lookup', 'shared', 'timeout')]
    assert backend.values('shared') == {}


@pytest.mark.parametrize('op,role,field', [('get', 'missing', 'cwd'), ('set', 'session', 'missing'),
    ('delete', 'project', 'color'), ('set', 'project', 'root'), ('delete', 'session', 'timeout')])
def test_unknown_and_forbidden_operations_fail_before_provider(fake, op, role, field):
    _, backend, space = fake
    with pytest.raises((KeyError, PermissionError)):
        getattr(space, op)(role, field, *(['value'] if op == 'set' else []))
    assert backend.calls() == []


@pytest.mark.parametrize('op', ['get', 'set', 'delete'])
def test_dataset_cannot_expand_view_capabilities(fake, op):
    owner, backend, _ = fake
    space = owner.materialize(mounts(session=view('restricted', [])))
    assert space.describe()['sets']['session']['fields']['cwd']['effective_operations'] == []
    with pytest.raises(PermissionError):
        getattr(space, op)('session', 'cwd', *(['/tmp/work'] if op == 'set' else []))
    assert backend.calls() == []
    # Missing view lookup rights never activate a default.
    with pytest.raises(PermissionError):
        space.get('session', 'timeout')
    assert backend.calls() == []


@pytest.mark.parametrize('case', ['missing', 'extra', 'duplicate', 'unbound', 'invalid-view', 'extra-key', 'not-list'])
def test_invalid_mounts_fail_without_provider_effect(fake, case):
    owner, backend, _ = fake
    table = mounts()
    if case == 'missing':
        table.pop()
    elif case == 'extra':
        table.append({**table[0], 'set': 'other'})
    elif case == 'duplicate':
        table.append(copy.deepcopy(table[0]))
    elif case == 'unbound':
        table[0]['provider_alias'] = 'unknown'
    elif case == 'invalid-view':
        table[0]['nolspace_view']['value']['caps'] = ['magic']
    elif case == 'extra-key':
        table[0]['token'] = 'not-part-of-mount-contract'
    else:
        table = {'session': table[0]}
    with pytest.raises(ValueError):
        owner.materialize(table)
    assert backend.calls() == []


def test_input_mutation_cannot_retarget_runtime(fake):
    owner, backend, _ = fake
    table = mounts()
    space = owner.materialize(table)
    table[0]['nolspace_view']['value']['target']['pool'] = 'other'
    table[0]['nolspace_view']['value']['caps'].clear()
    table[0]['provider_alias'] = 'unknown'
    table.clear()
    assert space.set('session', 'cwd', '/tmp/work') == '/tmp/work'
    assert backend.values('shared') == {'cwd': '/tmp/work'}
    assert backend.values('other') == {}


@pytest.mark.parametrize('value,kind', [('literal', 'string'), (7, 'integer'), (2.5, 'number'),
    (True, 'boolean'), (None, 'null'), ([1, False, None], 'array'), ({'nested': [3, None]}, 'object')])
def test_all_seven_native_types_remain_exact(sources, value, kind):
    replace(sources, 'fake/composition.toml', 'kind = "path"', 'kind = "any"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        backend, space = owner.backend(), owner.materialize(mounts())
        assert space.set('session', 'cwd', value) == value
        stored = backend.values('shared')['cwd']
        assert type(stored) is type(value)
        assert space.get('session', 'cwd') == value
        assert backend.calls() == [('upsert', 'shared', 'cwd'), ('lookup', 'shared', 'cwd')]
        if kind == 'boolean':
            assert stored is True


@pytest.mark.parametrize('value', [float('nan'), float('inf'), [float('-inf')],
    {'nested': [object()]}, {1: 'non-string key'}, (1, 2), b'bytes', object()])
def test_non_native_or_non_finite_contract_outputs_never_call_provider(sources, value):
    replace(sources, 'fake/composition.toml', 'kind = "path"', 'kind = "any"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        space = owner.materialize(mounts())
        with pytest.raises(ValueError) as caught:
            space.set('session', 'cwd', value)
        assert type(caught.value).__name__ == 'DataspaceNativeValueError'
        assert owner.backend().calls() == []


def test_cyclic_native_container_is_rejected_without_transport(sources):
    replace(sources, 'fake/composition.toml', 'kind = "path"', 'kind = "any"')
    value = []; value.append(value)
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        space = owner.materialize(mounts())
        with pytest.raises(ValueError, match='cycles'):
            space.set('session', 'cwd', value)
        assert owner.backend().calls() == []


@pytest.mark.parametrize('kind', ['invalid-default', 'non-native-default'])
def test_invalid_defaults_fail_materialization_before_effect(sources, kind):
    if kind == 'invalid-default':
        replace(sources, 'fake/session.toml', 'default = 5.0', 'default = "wrong"')
    else:
        replace(sources, 'fake/composition.toml', 'kind = "number"', 'kind = "bytes"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        with pytest.raises(ValueError) as caught:
            owner.materialize(mounts())
        expected = 'StrandInputValueError' if kind == 'invalid-default' else 'DataspaceNativeValueError'
        assert type(caught.value).__name__ == expected
        assert owner.backend().calls() == []


def test_multiple_roles_can_share_the_same_dataset_and_view(sources):
    replace(sources, 'fake/layout.toml', 'project = "project"', 'project = "session"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        shared = view('one')
        space = owner.materialize(mounts(shared, shared))
        assert space.set('session', 'cwd', 'same-value') == 'same-value'
        assert space.get('project', 'cwd') == 'same-value'
        assert set(space.describe()['sets']) == {'session', 'project'}
        assert space.describe()['sets']['project']['id'] == 'session'
        assert owner.backend().calls() == [('upsert', 'one', 'cwd'), ('lookup', 'one', 'cwd')]


def test_canonical_default_runs_both_boundaries_only_once(sources):
    replace(sources, 'fake/session.toml', 'contract = "path"', 'contract = "color"\ndefault = "#AABBCC"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        space = owner.materialize(mounts())
        assert owner.contract_calls('color') == [('input', '#AABBCC'), ('output', '#aabbcc')]
        for _ in range(3):
            assert space.get('session', 'cwd') == '#aabbcc'
        assert owner.contract_calls('color') == [('input', '#AABBCC'), ('output', '#aabbcc')]
        assert owner.backend().values('shared') == {}


@pytest.mark.parametrize('case', ['unbound-provider', 'private-function', 'root'])
def test_provider_binding_is_immediate_exposed_and_not_global(sources, case):
    if case == 'unbound-provider':
        replace(sources, 'fake/composition.toml', 'providers = ["backend"]', 'providers = ["other"]')
    elif case == 'private-function':
        replace(sources, 'fake_provider/composition.toml', '[functions.delete]\n', '')
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError):
        if case == 'root':
            graph.create('skaldos/stores/dataspace/core/runtime', {'layout': 'layout', 'providers': ['backend']})
        else:
            graph.create('local/dataspace/fake')


def test_norn_output_failure_after_write_is_not_caught_or_rolled_back(sources):
    replace(sources, 'fake/composition.toml', 'use = "local/dataspace/codec"\nconfig = { kind = "color" }',
            'use = "dix/norn/strand"\nconfig = { spec = "incompatible.strand.toml" }')
    parent = sources / 'compositions/fake'
    (parent / 'incompatible.strand.toml').write_text('[strand]\nid = "incompatible"\n'
        '[input]\ntype = "string"\n[output]\ntype = "number"\n')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        space = owner.materialize(mounts())
        with pytest.raises(ValueError) as caught:
            space.set('project', 'color', 'native-string')
        assert type(caught.value).__name__ == 'StrandOutputValueError'
        assert owner.backend().calls() == [('upsert', 'private', 'color')]
        assert owner.backend().values('private') == {'color': 'native-string'}


def test_default_output_error_is_preserved_before_any_provider_effect(sources):
    replace(sources, 'fake/composition.toml', 'use = "local/dataspace/codec"\nconfig = { kind = "path" }',
            'use = "dix/norn/strand"\nconfig = { spec = "incompatible.strand.toml" }')
    replace(sources, 'fake/session.toml', 'contract = "path"', 'contract = "path"\ndefault = "default"')
    (sources / 'compositions/fake/incompatible.strand.toml').write_text('[strand]\nid = "bad-default"\n'
        '[input]\ntype = "string"\n[output]\ntype = "number"\n')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        with pytest.raises(ValueError) as caught:
            owner.materialize(mounts())
        assert type(caught.value).__name__ == 'StrandOutputValueError'
        assert owner.backend().calls() == []


def test_recursive_layout_is_a_definition_error_without_provider_effect(sources):
    replace(sources, 'fake/layout.toml', 'session = "session"', 'session = "layout"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create('local/dataspace/fake')
        for _ in range(2):
            with pytest.raises(ValueError) as caught:
                owner.materialize(mounts())
            assert type(caught.value).__name__ == 'LayoutDefinitionError'
            assert owner.backend().calls() == []
