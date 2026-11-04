from __future__ import annotations

import copy
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def projection():
    # Pure local proposal class; no module graph, ROBA or VisiData dependency.
    package = types.ModuleType('projection_under_test')
    package.__path__ = [str(ROOT / 'cockpit/compositions/store_browser')]
    stub = types.ModuleType('projection_under_test.session')
    stub.BrowserSession = type('BrowserSession', (), {'safe': lambda self, text: text})
    sys.modules[package.__name__] = package
    sys.modules[stub.__name__] = stub
    spec = importlib.util.spec_from_file_location('projection_under_test.nolspace_session',
        ROOT / 'cockpit/compositions/store_browser/nolspace_session.py')
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        yield module.ComplexProjection
    finally:
        sys.modules.pop(stub.__name__)
        sys.modules.pop(package.__name__)


def test_nested_add_append_remove_detached_until_canonical_accept(projection):
    original = {'name': 'root', 'type': 'object', 'value': {'keep': True, 'nested': {'array': [1]}}}
    p = projection(original); p.enter('nested')
    inserted = {'child': []}
    proposal = p.add(inserted, 'new')
    assert p.root == original and p.path == ['nested']
    inserted['child'].append(7)
    assert proposal['value']['nested']['new'] == {'child': []}
    assert proposal['value']['keep'] is True
    p.accept(proposal); p.enter('array')
    proposal = p.add({'subtree': [2, None]})
    assert p.value == [1] and proposal['value']['nested']['array'] == [1, {'subtree': [2, None]}]
    p.accept(proposal)
    proposal = p.remove(1)
    assert p.value == [1, {'subtree': [2, None]}]
    assert proposal['value']['nested']['array'] == [1]
    p.accept(proposal); proposal = p.remove(0)
    assert p.value == [1] and proposal['value']['nested']['array'] == []
    p.accept(proposal); assert p.value == [] and p.path == ['nested', 'array']
    proposal = p.add({}); p.accept(proposal); p.enter(0)
    p.accept(p.add('filled', 'inside'))
    assert p.value == {'inside': 'filled'}
    assert original['value'] == {'keep': True, 'nested': {'array': [1]}}


def test_duplicate_invalid_remove_and_object_subtree_preserve_confirmed(projection):
    p = projection({'name': 'r', 'type': 'object', 'value': {'keep': 1, 'remove': {'tree': [1, 2]}}})
    before = copy.deepcopy(p.root)
    with pytest.raises(ValueError, match='already exists'): p.add(7, 'keep')
    with pytest.raises(TypeError): p.add(7)
    with pytest.raises(KeyError): p.remove('missing')
    assert p.root == before
    proposal = p.remove('remove')
    assert proposal['value'] == {'keep': 1} and p.root == before
    p.accept(proposal)
    p.accept(p.remove('keep'))
    assert p.value == {}
    p.accept(p.add([], 'new')); p.enter('new')
    for part in (-1, True, 0, '0'):
        with pytest.raises(IndexError): p.remove(part)
    assert p.value == []


def test_structural_canonical_result_keeps_or_truncates_current_path(projection):
    p = projection({'name': 'r', 'type': 'object', 'value': {'a': [{'b': {}}]}})
    p.enter('a'); p.enter(0); p.enter('b')
    proposal = p.add(False, 'leaf')
    assert p.accept(proposal) and p.path == ['a', 0, 'b']
    canonical = {'name': 'r', 'type': 'object', 'value': {'a': []}}
    assert not p.accept(canonical)
    assert p.root == canonical and p.path == ['a'] and p.value == []
