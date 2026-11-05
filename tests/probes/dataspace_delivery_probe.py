"""Real Dataspace process proof with source or wheel DIX/ROBA and delivered external roots."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import dix
import roba

root, mode = Path(sys.argv[1]).resolve(), sys.argv[2]
if mode == 'wheel':
    for package in (dix, roba):
        assert 'site-packages' in str(package.__file__)
sys.path.insert(0, str(root))
from tests._support.dataspace import DataspaceGraph, RobaScenario

assert 'visidata' not in sys.modules and '_curses' not in sys.modules
proof = {'mode': mode, 'surface': ['describe', 'get', 'set', 'delete']}
with DataspaceGraph(modules_root=root, roba=True) as graph, RobaScenario(graph) as scenario:
    assert scenario.private.get('session', 'timeout') == 5.0
    assert 'timeout' not in set(scenario.session.keys())
    assert scenario.private.set('session', 'cwd', '/delivery') == '/delivery'
    assert scenario.evia.get('session', 'cwd') == '/delivery'
    assert scenario.private.get('project', 'root') == '/projects/private'
    assert scenario.evia.get('project', 'root') == '/projects/evia'
    assert scenario.private.set('project', 'color', '#AABBCC') == '#aabbcc'
    assert scenario.evia.set('project', 'color', '#112233') == '#112233'
    assert scenario.targets['private'].get('color') == '#aabbcc'
    assert scenario.targets['evia'].get('color') == '#112233'
    assert scenario.private.delete('session', 'cwd') == {'set': 'session', 'field': 'cwd'}
    missing = graph.create('skaldos/stores/nolspace/core/contract').not_found_type()
    try:
        scenario.evia.get('session', 'cwd')
    except missing:
        pass
    else:
        raise AssertionError('Missing was not preserved')
    proof.update(default_not_materialized='timeout' not in set(scenario.session.keys()),
                 shared_session=True, isolated_projects=True, native_targets_verified=True,
                 stable_missing=True, description=scenario.private.describe())
assert not scenario.root.exists()
assert 'visidata' not in sys.modules and '_curses' not in sys.modules
proof.update(native_loader_unloaded=True, process_socket_and_temp_cleanup=True, no_ui_imports=True)
print(json.dumps(proof, sort_keys=True))
