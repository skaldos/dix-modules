"""Load/unload the exact installed launcher's module graph, without touching runtime state."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec


def main(launcher: Path) -> None:
    source = runpy.run_path(str(launcher))
    registry = create_core_component_registry()
    modules = registry.require('module', ModuleComponent)
    compositions = registry.require('composition', CompositionComponent)
    before = {name for name in sys.modules if name.startswith('_dix_composition_')}
    loaded = []
    created = False
    try:
        for name, path in source['MODULES']:
            modules.load_module(Path(path), module_id=name)
            loaded.append(name)
        bound = compositions.create_instance(CompositionInstanceSpec(
            'probe', 'skaldos/cockpit/tmux_workspace', {}, launcher.parent), owner_scope_id='split-delivery')
        created = True
        prefix = bound.runtime.__class__.__module__
        for suffix in ('', '.runtime_support', '.runtime_support.shared', '.runtime_support.lifecycle',
                       '.runtime_support.master', '.runtime_support.stores'):
            assert prefix + suffix in sys.modules, suffix
        assert issubclass(sys.modules[prefix].TmuxWorkspaceError, RuntimeError)
        assert len(bound.api.functions()) == 16
    finally:
        if created:
            compositions.destroy_instance('split-delivery', 'probe')
        for name in reversed(loaded):
            modules.unload_module(name)
    after = {name for name in sys.modules if name.startswith('_dix_composition_')}
    assert after == before, 'Dynamic composition imports leaked from the installed graph'
    print('Installed facade, sixteen functions and five support files loaded; native unload left no imports.')


if __name__ == '__main__':
    main(Path(sys.argv[1]))
