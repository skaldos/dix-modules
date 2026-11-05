from __future__ import annotations

import copy
import json
import os
import shlex
import time
from pathlib import Path

from cockpit_support.installed import installed_ui as installed_ui  # noqa: PLC0414
from cockpit_support.installed import nolspace_client as nolspace_client  # noqa: PLC0414
from cockpit_support.installed import real_owned_ui as real_owned_ui  # noqa: PLC0414
from cockpit_support.terminal import tmux, wait_for
from roba import RobaClient

ROOT = Path(__file__).parents[1]


def test_installed_structural_root_proposals_and_reader(nolspace_client):
    installed, _client = nolspace_client
    create, workspace, _, started, binary, _, root = installed
    runtime = create('skaldos/cockpit/roba_runtime').api
    env = runtime.require('owner_environment')(session='b')
    context = RobaClient(env=env).control().context_create(context_id='n69')
    owner = RobaClient(env={}).context(locator='unix:' + context['socket'], token=context['owner_token'])
    initial = {'object-root': {'existing': 'keep', 'nested': {}}, 'array-root': ['first'],
               'delete-root': {'keep': True, 'remove': {'whole': ['subtree']}}}
    for name, value in initial.items(): owner.set(name, value)
    tokens = {name: owner.token_create(token_id=name, read=['context'], **rights)['token']
              for name, rights in [('rw', {'write': ['context']}), ('reader', {})]}
    catalog = create('skaldos/cockpit/store_browser').runtime.catalog
    base = {'context_id': 'n69', 'context_locator': 'unix:' + context['socket'], 'timeout': 2.0}
    for name, token in tokens.items():
        catalog.require('create')({'store_id': name, 'provider': 'roba',
                                  'connection': {**base, 'token': token}}, 'a')
    trace = root / 'trace'; trace.mkdir()
    wrapper = binary / 'dix-cockpit-store-browser'
    wrapper.write_text(wrapper.read_text().replace('"$DIX_LAUNCHERS/dix-cockpit-store-browser.py"',
        shlex.quote(str(ROOT / 'tests/probes/structural_interaction_probe.py')) + ' ' +
        shlex.quote(str(ROOT / 'tests/probes/nolspace_installed_probe.py')) + ' ' +
        '"$DIX_LAUNCHERS/dix-cockpit-store-browser.py" ' + shlex.quote(str(trace))))
    sock = started['tmux']['socket']
    def screen(pane): return tmux(sock, 'capture-pane', '-p', '-t', pane)
    def at(pane, suffix):
        try:
            wait_for(lambda: screen(pane).splitlines()[0].rstrip(' ║~').endswith(suffix))
        except AssertionError:
            raise AssertionError('Expected breadcrumb ' + suffix + '\n' + screen(pane) + '\n' +
                                 '\n'.join((trace / 'rw-interaction.jsonl').read_text().splitlines()[-15:])) from None
    def keys(pane, *values):
        tmux(sock, 'send-keys', '-t', pane, *values); time.sleep(.14)
    def literal(pane, value):
        tmux(sock, 'send-keys', '-t', pane, '-l', '--', value); keys(pane, 'Enter')
    def select(pane, index, column=0):
        keys(pane, 'h', 'h', 'g', 'g')
        for _ in range(index): keys(pane, 'j')
        for _ in range(column): keys(pane, 'l')
    def command(pane, name): keys(pane, ':'); literal(pane, name)
    def new(pane, kind, value=None, name=None):
        command(pane, 'n'); literal(pane, kind)
        if name is not None: literal(pane, name)
        if kind != 'null': literal(pane, value)
    def calls(name):
        path = trace / (name + '.jsonl')
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def effects(name): return [c for c in calls(name) if '/state/' in c['path']]
    def opened(name):
        result = workspace.require('open_store')(store_id=name,
            revision=catalog.require('record')(name, 'a')['revision'], session='a')
        pane = result['panes']['browser']['pane_id']
        wait_for(lambda: 'instances' in screen(pane))
        keys(pane, 'Enter'); wait_for(lambda: 'object-root' in screen(pane))
        return result, pane
    result, pane = opened('rw')
    assert effects('rw') == []
    names = owner.keys()
    select(pane, names.index('object-root'), 1); keys(pane, 'Enter')
    wait_for(lambda: len(effects('rw')) == 1)
    keys(pane, 'Enter')
    new(pane, 'integer', '42', 'number')
    wait_for(lambda: owner.get('object-root').get('number') == 42)
    before = list(effects('rw'))
    command(pane, 'n'); literal(pane, 'integer'); literal(pane, 'number')
    wait_for(lambda: 'already exists' in screen(pane))
    assert effects('rw') == before and owner.get('object-root')['number'] == 42
    new(pane, 'array', '[]', 'rows')
    wait_for(lambda: owner.get('object-root').get('rows') == [])
    select(pane, 3, 2); keys(pane, 'Enter')
    wait_for(lambda: '0 rows' in screen(pane))
    new(pane, 'object', '{}')
    wait_for(lambda: owner.get('object-root')['rows'] == [{}])
    select(pane, 0, 2); keys(pane, 'Enter')
    new(pane, 'boolean', 'true', 'enabled')
    wait_for(lambda: owner.get('object-root')['rows'] == [{'enabled': True}])
    keys(pane, 'q'); at(pane, '/ object-root / rows')
    new(pane, 'array', '[]')
    wait_for(lambda: owner.get('object-root')['rows'] == [{'enabled': True}, []])
    select(pane, 1, 2); keys(pane, 'Enter'); at(pane, '/ object-root / rows / 1')
    new(pane, 'string', 'deep')
    wait_for(lambda: owner.get('object-root')['rows'] == [{'enabled': True}, ['deep']])
    keys(pane, 'q'); at(pane, '/ object-root / rows'); select(pane, 0)
    before = list(effects('rw')); command(pane, 'd'); wait_for(lambda: 'confirm' in screen(pane)); keys(pane, 'n')
    assert effects('rw') == before
    at(pane, '/ object-root / rows')
    command(pane, 'd'); wait_for(lambda: 'confirm' in screen(pane)); keys(pane, 'y')
    try:
        wait_for(lambda: owner.get('object-root')['rows'] == [['deep']])
    except AssertionError:
        raise AssertionError(screen(pane) + '\n' + str(effects('rw'))) from None
    keys(pane, 'q'); select(pane, 2)  # number
    command(pane, 'd'); wait_for(lambda: 'confirm' in screen(pane)); keys(pane, 'y')
    expected = {'existing': 'keep', 'nested': {}, 'rows': [['deep']]}
    wait_for(lambda: owner.get('object-root') == expected)
    root_calls = [c for c in effects('rw') if c['path'].endswith('/state/object-root')]
    assert [c['method'] for c in root_calls] == ['GET'] + ['PUT'] * 8
    # Distinct roots: append only at the end and delete the complete selected subtree.
    keys(pane, 'q'); select(pane, names.index('array-root'), 2); keys(pane, 'Enter', 'Enter')
    new(pane, 'integer', '2')
    wait_for(lambda: owner.get('array-root') == ['first', 2])
    keys(pane, 'q'); select(pane, names.index('delete-root'), 2); keys(pane, 'Enter', 'Enter')
    select(pane, 1); command(pane, 'd'); wait_for(lambda: 'confirm' in screen(pane)); keys(pane, 'y')
    wait_for(lambda: owner.get('delete-root') == {'keep': True})
    assert [c['method'] for c in effects('rw')] == ['GET'] + ['PUT'] * 8 + ['GET', 'PUT', 'GET', 'PUT']
    assert not any(c['method'] == 'DELETE' for c in calls('rw'))
    # Reader can reach identical local containers, but no prompts or mutation requests.
    _, reader = opened('reader')
    select(reader, names.index('object-root')); keys(reader, 'Enter', 'Enter')
    for token in ('n', 'd'):
        command(reader, token); wait_for(lambda: 'does not offer upsert' in screen(reader))
    assert [c['method'] for c in effects('reader')] == ['GET']
    # A rejected provider call does not turn the local proposal into a confirmed state.
    reopened = workspace.require('open_store')(store_id='rw',
        revision=catalog.require('record')('rw', 'a')['revision'], session='a')
    assert reopened['window_id'] == result['window_id']
    final = copy.deepcopy(owner.state())
    owner.token_delete(token_id='rw')
    new(pane, 'string', 'not-accepted', 'forbidden')
    wait_for(lambda: 'Error' in screen(pane))
    assert owner.state() == final
    assert tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead}') == '0'
    assert final == {'object-root': expected, 'array-root': ['first', 2], 'delete-root': {'keep': True}}
    secrets = [context['owner_token'], env['ROBA_CONTROL_TOKEN'], *tokens.values()]
    metadata = tmux(sock, 'show-environment', '-t', 'a')
    metadata += tmux(sock, 'show-options', '-w', '-t', result['window_id'])
    metadata += tmux(sock, 'list-panes', '-t', result['window_id'], '-F', '#{pane_start_command} #{pane_title}')
    assert not any(secret in metadata or secret in screen(pane) for secret in secrets)
    if os.environ.get('DIX_STRUCTURAL_EVIDENCE_DIR'):
        out = Path(os.environ['DIX_STRUCTURAL_EVIDENCE_DIR']); out.mkdir(parents=True, exist_ok=True)
        (out / 'structural-proof.json').write_text(json.dumps({
            'object_root_methods': [c['method'] for c in root_calls],
            'all_value_methods': [c['method'] for c in effects('rw')],
            'reader_methods': [c['method'] for c in effects('reader')],
            'object_add_array_append_empty_nested_fill_subtree_delete': True,
            'duplicate_and_cancel_no_write': True, 'provider_rejected_no_commit': True,
            'same_window_reopened': True, 'secret_transport': False,
        }, indent=2) + '\n')
        for name in ('rw', 'reader'):
            (out / (name + '-endpoints.json')).write_text(json.dumps(calls(name), indent=2) + '\n')
