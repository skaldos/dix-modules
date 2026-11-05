from __future__ import annotations

import shutil
from dataclasses import FrozenInstanceError

import pytest
from dix.core.composition import CompositionComponentError, CompositionOwnerBindingError
from dix.core.composition.runtime import CompositionRuntimeError

from tests._support.dataspace import ROOT, DataspaceGraph


@pytest.fixture
def sources(tmp_path):
    root = tmp_path / 'module'
    shutil.copytree(ROOT / 'tests/fixtures/dataspace', root)
    return root


def edit(root, file, old, new):
    path = root / 'compositions' / file
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def causes(error):
    # The existing loader wraps construction failures; assert the precise original cause too.
    while error is not None:
        yield error
        error = error.__cause__


def test_source_definitions_are_local_immutable_and_metadata_detached():
    with DataspaceGraph() as graph:
        owner = graph.create()
        layout = owner.definition()
        assert layout.id == 'runtime' and set(layout.sets) == {'session', 'project'}
        session = layout.sets['session']
        assert session.fields['timeout'].default_value() == 5.0
        assert session.fields['cwd'].operations == ('get', 'set', 'delete')
        assert owner.contract_calls('number') == [('input', 5.0), ('output', 5.0)]
        for _ in range(3):
            assert owner.definition() is layout
            session.fields['timeout'].default_value()
            metadata = layout.describe()
            metadata['sets']['session']['fields']['timeout']['operations'].clear()
        assert owner.contract_calls('number') == [('input', 5.0), ('output', 5.0)]
        assert layout.describe()['sets']['session']['fields']['timeout'] == {
            'contract': 'number', 'operations': ['get', 'set'], 'has_default': True}
        assert '5.0' not in str(layout.describe())
        with pytest.raises(FrozenInstanceError):
            layout.id = 'changed'
        with pytest.raises(TypeError):
            layout.sets['extra'] = session
        with pytest.raises(FrozenInstanceError):
            session.fields['timeout'].contract = 'changed'
        with pytest.raises(TypeError):
            session.fields['extra'] = session.fields['cwd']


@pytest.mark.parametrize('file,old,new', [
    ('definitions/session.toml', '[dataset]', 'unknown = 1\n[dataset]'),
    ('definitions/session.toml', 'id = "session"', 'id = "session"\nunknown = true'),
    ('definitions/session.toml', 'contract = "path"', 'contract = "path"\nunknown = 2'),
    ('definitions/session.toml', 'contract = "path"', 'contract = "global/path"'),
    ('definitions/session.toml', '[fields.cwd]', '[fields.""]'),
    ('definitions/session.toml', '[fields.cwd]', '[fields.cwd]\ndefault = 1\ndefault = 2'),
    ('definitions/session.toml', '["get", "set", "delete"]', '["get", "get"]'),
    ('definitions/session.toml', '["get", "set", "delete"]', '["patch"]'),
    ('definitions/session.toml', '["get", "set", "delete"]', '"get"'),
    ('definitions/layout.toml', '[layout]', 'unknown = 1\n[layout]'),
    ('definitions/layout.toml', 'id = "runtime"', 'id = ""'),
    ('definitions/layout.toml', 'project = "project"', 'project = { nested = "project" }'),
    ('definitions/layout.toml', 'project = "project"', 'session = "project"'),
])
def test_invalid_source_rejected_before_any_runtime(sources, file, old, new):
    edit(sources, file, old, new)
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError) as caught:
        graph.create()
    assert any(type(exc).__name__ in {'DatasetDefinitionError', 'LayoutDefinitionError'}
               for exc in causes(caught.value))


@pytest.mark.parametrize('alias', ['path', 'session'])
def test_unknown_owner_dependency_cannot_resolve_from_globals(sources, alias):
    file = 'definitions/session.toml' if alias == 'path' else 'definitions/layout.toml'
    edit(sources, file, '"' + alias + '"', '"unbound"')
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError) as caught:
        graph.create()
    assert any(isinstance(exc, CompositionOwnerBindingError) for exc in causes(caught.value))


def test_existing_private_method_is_not_a_contract_export(sources):
    edit(sources, 'codec/composition.toml', '[functions.process_output]\n', '')
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError) as caught:
        graph.create()
    assert any(isinstance(exc, CompositionOwnerBindingError) and 'undeclared' in str(exc)
               for exc in causes(caught.value))


@pytest.mark.parametrize('composition', ['dataset', 'layout'])
def test_root_use_requires_immediate_owner(sources, composition):
    path = sources / 'compositions/definitions'
    model = 'session.toml' if composition == 'dataset' else 'layout.toml'
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError) as caught:
        graph.create('skaldos/stores/dataspace/core/' + composition, {'model': model}, path)
    assert any(isinstance(exc, CompositionRuntimeError) and 'immediate composition owner' in str(exc)
               for exc in causes(caught.value))


@pytest.mark.parametrize('composition', ['dataset', 'layout'])
@pytest.mark.parametrize('escape', ['absolute', 'parent', 'symlink'])
def test_owner_source_paths_cannot_escape(sources, tmp_path, composition, escape):
    file = 'session.toml' if composition == 'dataset' else 'layout.toml'
    outside = (sources if escape == 'symlink' else tmp_path) / 'outside.toml'
    outside.write_text((sources / 'compositions/definitions' / file).read_text())
    if escape == 'absolute':
        target = str(outside)
    elif escape == 'parent':
        target = '../../../outside.toml'
    else:
        link = sources / 'compositions/definitions/link.toml'
        link.symlink_to(outside)
        target = 'link.toml'
    edit(sources, 'definitions/composition.toml', f'model = "{file}"', f'model = "{target}"')
    with DataspaceGraph(sources) as graph, pytest.raises(CompositionComponentError) as caught:
        graph.create()
    assert any(type(exc).__name__ in {'DatasetDefinitionError', 'LayoutDefinitionError'}
               and 'inside its owner' in str(exc) for exc in causes(caught.value))


def test_same_contract_alias_has_owner_local_meaning(sources):
    with DataspaceGraph() as first:
        a = first.create().definition().sets['project'].fields['root']
        edit(sources, 'definitions/composition.toml', 'kind = "path"', 'kind = "path", prefix = "other:"')
        with DataspaceGraph(sources) as second:
            b = second.create().definition().sets['project'].fields['root']
            assert a.decode('value') == 'value'
            assert b.decode('value') == 'other:value'


def test_dataset_reuse_and_source_edits_do_not_change_loaded_definitions(sources):
    edit(sources, 'definitions/layout.toml', 'project = "project"', 'project = "session"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create()
        layout = owner.definition()
        assert layout.sets['session'] is layout.sets['project']
        edit(sources, 'definitions/session.toml', 'default = 5.0', 'default = 9.0')
        assert layout.sets['session'].fields['timeout'].default_value() == 5.0
        assert owner.contract_calls('number') == [('input', 5.0), ('output', 5.0)]


def test_invalid_default_preserves_norn_input_error_before_materialization(sources):
    edit(sources, 'definitions/session.toml', 'default = 5.0', 'default = "invalid"')
    with DataspaceGraph(sources) as graph:
        owner = graph.create()
        with pytest.raises(ValueError) as caught:
            owner.definition()
        assert type(caught.value).__name__ == 'StrandInputValueError'
        assert owner.contract_calls('number') == [('input', 'invalid')]


def test_modelled_identity_contract_default_is_canonical_and_detached(sources):
    edit(sources, 'definitions/composition.toml', 'use = "local/dataspace/codec"\nconfig = { kind = "path" }',
         'use = "dix/norn/strand"\nconfig = { spec = "payload.strand.toml" }')
    edit(sources, 'definitions/session.toml', 'operations = ["get", "set", "delete"]',
         'operations = ["get", "set", "delete"]\ndefault = { title = "test", enabled = true }')
    parent = sources / 'compositions/definitions'
    (parent / 'payload.toml').write_text('name = "Payload"\n[fields.title]\ntype = "string"\n'
                                        '[fields.enabled]\ntype = "boolean"\n')
    (parent / 'payload.strand.toml').write_text('[strand]\nid = "payload"\n[input]\ntype = "model"\n'
        'model = "payload.toml"\n[output]\ntype = "model"\nmodel = "payload.toml"\n')
    with DataspaceGraph(sources) as graph:
        field = graph.create().definition().sets['session'].fields['cwd']
        value = field.default_value()
        assert value == {'title': 'test', 'enabled': True}
        value['title'] = 'changed'
        assert field.default_value()['title'] == 'test'
        assert field.encode({'title': 'new', 'enabled': False})[0] == 'object'
        with pytest.raises(ValueError) as caught:
            field.encode({'title': 1, 'enabled': False})
        assert type(caught.value).__name__ == 'StrandInputValueError'
