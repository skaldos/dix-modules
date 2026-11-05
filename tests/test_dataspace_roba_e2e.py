from __future__ import annotations

import copy
import shutil

import pytest
from roba.transport import TransportClient

from tests._support.dataspace import ROOT, DataspaceGraph, RobaScenario


def test_real_roba_context_instance_shared_state_and_isolated_projects(monkeypatch):
    with DataspaceGraph(roba=True) as graph, RobaScenario(graph) as scenario:
        calls = []
        original = TransportClient.request
        def spy(self, method, path, **kwargs):
            assert 'snapshot' not in path
            calls.append((method, path))
            return original(self, method, path, **kwargs)
        monkeypatch.setattr(TransportClient, 'request', spy)
        private, evia = scenario.private, scenario.evia
        description = private.describe()
        assert calls == []
        assert description['sets']['session']['fields']['timeout']['has_default']
        assert not any(secret in str(description) for secret in
            (scenario.session_connection['token'], scenario.project_connection['token']))
        assert private.get('session', 'timeout') == 5.0
        assert len(calls) == 2 and calls[-1][1].endswith('/state/timeout')
        assert 'timeout' not in set(scenario.session.keys())
        calls.clear()
        assert private.set('session', 'cwd', '/shared/work') == '/shared/work'
        assert [method for method, _ in calls] == ['GET', 'PUT']
        assert evia.get('session', 'cwd') == '/shared/work'
        assert scenario.session.get('cwd') == '/shared/work'
        assert private.get('project', 'root') == '/projects/private'
        assert evia.get('project', 'root') == '/projects/evia'
        calls.clear()
        with pytest.raises(ValueError, match='Invalid test color'):
            private.set('project', 'color', 'bad')
        with pytest.raises(PermissionError):
            private.set('project', 'root', '/forbidden')
        assert calls == []
        assert private.set('project', 'color', '#AABBCC') == '#aabbcc'
        assert [method for method, _ in calls] == ['GET', 'PUT']
        assert evia.set('project', 'color', '#112233') == '#112233'
        assert scenario.targets['private'].get('color') == '#aabbcc'
        assert scenario.targets['evia'].get('color') == '#112233'
        calls.clear()
        assert private.delete('session', 'cwd') == {'set': 'session', 'field': 'cwd'}
        assert [method for method, _ in calls] == ['GET', 'DELETE']
        assert 'cwd' not in set(scenario.session.keys())
        missing = graph.create('skaldos/stores/nolspace/core/contract').not_found_type()
        with pytest.raises(missing):
            evia.get('session', 'cwd')
        assert scenario.session.keys() == []


def test_real_bad_credentials_native_capabilities_and_transport_do_not_activate_default(monkeypatch):
    with DataspaceGraph(roba=True) as graph, RobaScenario(graph) as scenario:
        missing = graph.create('skaldos/stores/nolspace/core/contract').not_found_type()
        monkeypatch.setenv('ROBA_CTX_TOKEN', scenario.session_connection['token'])
        monkeypatch.setenv('ROBA_CONTEXT', scenario.session_connection['context_locator'])
        for case in ('credential', 'rights', 'transport'):
            table = copy.deepcopy(scenario.mounts())
            conn = table[0]['nolspace_view']['value']['target']['connection']
            if case == 'credential':
                conn['token'] = 'invalid-explicit-token'
            elif case == 'rights':
                conn['token'] = scenario.session.token_create(token_id='writer', write=['context'])['token']
            else:
                conn['context_locator'] = 'unix:' + str(scenario.root / 'absent.sock')
            space = scenario.owner.materialize(table)
            with pytest.raises(RuntimeError) as caught:
                space.get('session', 'timeout')
            assert not isinstance(caught.value, missing)
            assert conn['token'] not in str(caught.value)
        assert 'timeout' not in set(scenario.session.keys())
        assert scenario.private.get('session', 'timeout') == 5.0


def test_isolated_delivered_roots_use_real_loader_and_missing_identity(tmp_path):
    delivered = tmp_path / 'delivered'
    for relative in ('stores/nolspace/core', 'stores/nolspace/roba', 'stores/dataspace/core',
                     'tests/fixtures/dataspace', 'tests/fixtures/dataspace_roba'):
        shutil.copytree(ROOT / relative, delivered / relative, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    with DataspaceGraph(modules_root=delivered, roba=True) as graph, RobaScenario(graph) as scenario:
        first = graph.create('skaldos/stores/nolspace/core/contract').not_found_type()
        second = graph.create('skaldos/stores/nolspace/core/contract').not_found_type()
        assert first is second
        assert scenario.private.get('session', 'timeout') == 5.0
        assert scenario.private.set('session', 'cwd', '/delivered') == '/delivered'
        assert scenario.evia.get('session', 'cwd') == '/delivered'
        assert scenario.private.delete('session', 'cwd') == {'set': 'session', 'field': 'cwd'}
        with pytest.raises(first):
            scenario.evia.get('session', 'cwd')
        assert scenario.session.keys() == []
    # DataspaceGraph.close asserts native module unload; RobaScenario.close asserts PID/socket/temp cleanup.
    assert not scenario.root.exists()
