from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]
WORKSPACE = ROOT / 'cockpit/compositions/tmux_workspace'
CONTRACT = json.loads((ROOT / 'tests/fixtures/cockpit_tmux_contract.json').read_text())


class OriginalDependencyNames(ast.NodeTransformer):
    """Normalize only the explicit dependency receiver introduced by this refactor."""

    def visit_Attribute(self, node):
        node = self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == 'self':
            if node.attr in {'_tmux', '_lifecycle'}:
                return ast.Name(id='self', ctx=ast.Load())
            if node.attr == '_source_file':
                return ast.Call(func=ast.Name(id='Path', ctx=ast.Load()),
                                args=[ast.Name(id='__file__', ctx=ast.Load())], keywords=[])
        return node


def dump(node):
    return ast.dump(node, include_attributes=False)


def classes():
    files = [WORKSPACE / 'runtime.py', *(WORKSPACE / 'runtime_support').glob('*.py')]
    return {node.name: node for path in files for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.ClassDef)}


def test_exact_base_facade_signatures_and_unchanged_implementation_bodies():
    assert hashlib.sha256((WORKSPACE / 'composition.toml').read_bytes()).hexdigest() == CONTRACT['composition_sha256']
    types = classes()
    facade = {n.name: n for n in types['Runtime'].body if isinstance(n, ast.FunctionDef)}
    assert {n for n in facade if not n.startswith('_')} == set(CONTRACT['signatures']) - {'__init__'}
    assert '__getattr__' not in facade
    for name, signature in CONTRACT['signatures'].items():
        method = facade[name]
        assert dump(method.args) == signature['args'], name
        assert (dump(method.returns) if method.returns else None) == signature['returns'], name
    # Each old implementation body remains whole, including commands, raises and rollback.
    # No golden result is regenerated from the refactored source.
    for name, expected in CONTRACT['bodies'].items():
        implementations = [n for cls in types.values() if cls.name != 'Runtime'
                           for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name]
        assert len(implementations) <= 1, name
        method = implementations[0] if implementations else facade[name]
        actual = '\n'.join(dump(OriginalDependencyNames().visit(n)) for n in method.body)
        assert hashlib.sha256(actual.encode()).hexdigest() == expected, name


def test_low_level_constants_validators_and_error_import_are_preserved(store_graph):
    tree = ast.parse((WORKSPACE / 'runtime_support/shared.py').read_text())
    constants = {n.targets[0].id: dump(n.value) for n in tree.body if isinstance(n, ast.Assign)}
    functions = {n.name: dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert constants == CONTRACT['constants']
    assert functions == CONTRACT['functions']
    create, _, _ = store_graph
    bound = create('skaldos/cockpit/tmux_workspace')
    module = sys.modules[bound.runtime.__class__.__module__]
    shared = sys.modules[module.__name__ + '.runtime_support.shared']
    assert module.TmuxWorkspaceError is shared.TmuxWorkspaceError
    assert issubclass(module.TmuxWorkspaceError, RuntimeError)


def test_real_loader_removes_facade_and_all_package_local_modules(tmp_path):
    registry = create_core_component_registry()
    modules = registry.require('module', ModuleComponent)
    compositions = registry.require('composition', CompositionComponent)
    loaded = []
    prefix = None
    created = False
    try:
        for name in ('dix/state', 'dix/cli', 'dix/norn', 'dix/roba'):
            modules.load_module(first_party_module_path(name), module_id=name)
            loaded.append(name)
        for name, relative in (
            ('skaldos/stores/nolspace/core', 'stores/nolspace/core'),
            ('skaldos/stores/nolspace/roba', 'stores/nolspace/roba'),
            ('skaldos/visidata', 'visidata'), ('skaldos/cockpit', 'cockpit'),
        ):
            modules.load_module(ROOT / relative, module_id=name)
            loaded.append(name)
        for index in range(2):
            bound = compositions.create_instance(CompositionInstanceSpec(
                'split', 'skaldos/cockpit/tmux_workspace', {}, tmp_path), owner_scope_id='split-test')
            created = True
            prefix = bound.runtime.__class__.__module__
            assert prefix in sys.modules
            assert prefix + '.runtime_support.shared' in sys.modules
            assert prefix + '.runtime_support.lifecycle' in sys.modules
            assert bound.api.require('config_path')() == ROOT / 'cockpit/integrations/tmux/cockpit.conf'
            compositions.destroy_instance('split-test', 'split')
            created = False
            # Definitions remain loaded after instance destruction. The real module
            # unload below owns import cleanup; the test never removes imports itself.
            assert prefix in sys.modules
    finally:
        if created:
            compositions.destroy_instance('split-test', 'split')
        for name in reversed(loaded):
            modules.unload_module(name)
    assert prefix is not None
    assert not any(n == prefix or n.startswith(prefix + '.') for n in sys.modules)
