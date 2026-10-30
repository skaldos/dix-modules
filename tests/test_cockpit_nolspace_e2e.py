from __future__ import annotations

import fcntl
import json
import os
import pty
import shlex
import struct
import subprocess
import termios
import time
from pathlib import Path

import pytest
from roba import RobaClient
from test_cockpit_interaction_install import (
    installed_ui as installed_ui,  # noqa: PLC0414 - dependency of the shared real fixture
)
from test_cockpit_owned_store_e2e import (
    real_owned_ui as real_owned_ui,  # noqa: PLC0414 - shared real installed tmux/PTY fixture
)
from test_cockpit_store_workspace import drain_terminal, tmux, wait_for

ROOT = Path(__file__).parents[1]


@pytest.fixture
def nolspace_client(real_owned_ui):
    sock = real_owned_ui[3]['tmux']['socket']
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 45, 160, 0, 0))
    process = subprocess.Popen(['tmux', '-S', sock, 'attach-session', '-t', 'a'],
        stdin=slave, stdout=slave, stderr=slave,
        env={**os.environ, 'TERM': 'xterm-256color', 'TMUX': ''})
    os.close(slave); drain_terminal(master)
    try:
        yield real_owned_ui, master
    finally:
        process.terminate(); process.wait(timeout=5); os.close(master)


def test_real_installed_nolspace_atomic_mutation_rights_copy_and_paste(nolspace_client):
    real_owned_ui, client_fd = nolspace_client
    create, workspace, _, started, binary, _launchers, root = real_owned_ui
    runtime = create('skaldos/cockpit/roba_runtime').api
    env = runtime.require('owner_environment')(session='b')
    context = RobaClient(env=env).control().context_create(context_id='n69')
    owner = RobaClient(env={}).context(locator='unix:' + context['socket'], token=context['owner_token'])
    long = 'complete clipboard $text; ' + 'z' * 900
    initial = {'same': 'context conflict', 'text': 'original', 'integer': 7, 'number': 1.5,
               'boolean': True, 'null': None, 'array': [1, {'message': 'nested'}],
               'object': {'items': [False, None]}, 'long': long}
    for key, value in initial.items(): owner.set(key, value)
    owner.instance_create(instance_id='same', state={**initial, 'same': 'instance conflict'})
    rights = {'rw': {'read': ['context', 'instance:same'], 'write': ['context', 'instance:same']},
              'ro': {'read': ['context', 'instance:same']}, 'wo': {'write': ['instance:same']}}
    tokens = {name: owner.token_create(token_id=name, **caps)['token'] for name, caps in rights.items()}
    secrets = [context['owner_token'], env['ROBA_CONTROL_TOKEN'], *tokens.values()]
    base = {'context_id': 'n69', 'context_locator': 'unix:' + context['socket'], 'timeout': 2.0}
    catalog = create('skaldos/cockpit/store_browser').runtime.catalog
    for name in ('rw', 'ro', 'wo'):
        catalog.require('create')({'store_id': name, 'provider': 'roba',
            'connection': {**base, 'token': tokens[name], 'instance_id': 'same'}}, 'a')
    catalog.require('create')({'store_id': 'context', 'provider': 'roba',
                              'connection': {**base, 'token': tokens['rw']}}, 'a')
    trace = root / 'trace'; trace.mkdir()
    wrapper = binary / 'dix-cockpit-store-browser'
    wrapper.write_text(wrapper.read_text().replace(
        '"$DIX_LAUNCHERS/dix-cockpit-store-browser.py"',
        shlex.quote(str(ROOT / 'tests/probes/nolspace_installed_probe.py')) + ' ' +
        '"$DIX_LAUNCHERS/dix-cockpit-store-browser.py" ' + shlex.quote(str(trace))))
    sock = started['tmux']['socket']
    for variable in ('WAYLAND_DISPLAY', 'DISPLAY'):
        tmux(sock, 'set-environment', '-t', 'a', variable, '')
    proof = {'rights': {}, 'lazy': {}, 'clipboard': {}, 'secret_transport': False}

    def screen(pane): return tmux(sock, 'capture-pane', '-p', '-t', pane)
    def keys(pane, *values):
        tmux(sock, 'send-keys', '-t', pane, *values); time.sleep(.13)
    def command(pane, token):
        keys(pane, ':'); keys(pane, token, 'Enter')
    def literal(pane, value):
        tmux(sock, 'send-keys', '-t', pane, '-l', '--', value)
        keys(pane, 'Enter')
    def calls(name):
        path = trace / (name + '.jsonl')
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def values(name):
        return [call for call in calls(name) if '/state/' in call['path']]
    def opened(name):
        result = workspace.require('open_store')(
            store_id=name, revision=catalog.require('record')(name, 'a')['revision'], session='a')
        pane = result['panes']['browser']['pane_id']
        wait_for(lambda: 'Nolspace' in screen(pane))
        if name == 'wo': wait_for(lambda: 'No enumerate' in screen(pane))
        elif name == 'context': wait_for(lambda: 'instances' in screen(pane))
        else: wait_for(lambda: 'text' in screen(pane))
        return result, pane
    def choose(pane, name, names=None):
        keys(pane, 'h', 'h', 'g', 'g')
        if names is None: names = list(initial)
        # Native state-key order is the SDK order, not inferred from preview values.
        for _ in range(names.index(name)): keys(pane, 'Down')
    instance = owner.with_scope('id:same')
    names = instance.keys()
    result, pane = opened('rw')
    assert values('rw') == []
    choose(pane, 'text', names); keys(pane, 'Enter')
    wait_for(lambda: len(values('rw')) == 1)
    assert values('rw')[0]['method'] == 'GET'
    keys(pane, 'Enter'); literal(pane, 'edited')
    wait_for(lambda: instance.get('text') == 'edited')
    assert [c['method'] for c in values('rw')] == ['GET', 'PUT']
    keys(pane, 'Enter'); tmux(sock, 'send-keys', '-t', pane, '-l', 'cancelled')
    keys(pane, 'Escape'); time.sleep(.35)
    assert instance.get('text') == 'edited' and len(values('rw')) == 2
    proof['lazy'] = {'initial_value_reads': 0, 'explicit_lookup': 1, 'accepted_upsert': 1,
                     'cancelled_writes': 0}
    # Every standard atomic gets a real native write via the installed prompt, including null.
    for kind, raw, expected in [('string', 'plain unquoted', 'plain unquoted'), ('integer', '-9', -9),
                                ('number', '2.75', 2.75), ('boolean', 'false', False), ('null', None, None)]:
        command(pane, 'n'); literal(pane, kind); literal(pane, 'created')
        if raw is not None: literal(pane, raw)
        wait_for(lambda expected=expected: instance.get('created') == expected)
    before = list(values('rw'))
    command(pane, 'n'); literal(pane, 'integer'); literal(pane, 'bad-parse'); literal(pane, 'true')
    wait_for(lambda: 'valid integer' in screen(pane))
    assert values('rw') == before
    # Copy uses full underlying long string, with no hidden extra lookup.
    choose(pane, 'long', names); keys(pane, 'Enter')
    before = len(values('rw'))
    keys(pane, 'y')
    wait_for(lambda: tmux(sock, 'save-buffer', '-') == long)
    assert len(values('rw')) == before
    # Real prefix in a browser value editor: paste the buffer and accept once.
    choose(pane, 'text', names); keys(pane, 'Enter'); keys(pane, 'Enter')
    tmux(sock, 'select-pane', '-t', pane)
    os.write(client_fd, b'\x01p'); time.sleep(.5); keys(pane, 'Enter')
    wait_for(lambda: instance.get('text') == long)
    proof['clipboard'] = {'full_characters': len(long), 'browser_prefix_paste': True}
    choose(pane, 'created', names + ['created'])
    command(pane, 'd'); literal(pane, 'yes')
    wait_for(lambda: 'created' not in list(instance.keys()))
    proof['rights']['rw'] = {'all_atomics': True, 'cancel_no_write': True, 'delete_once': True}
    # Read-only: no target mutation request, before or after trying all paths.
    _, ro = opened('ro')
    choose(ro, 'text', names); keys(ro, 'Enter')
    count = len(values('ro'))
    keys(ro, 'Enter'); command(ro, 'n'); command(ro, 'd')
    wait_for(lambda: 'does not offer' in screen(ro))
    assert len(values('ro')) == count and all(c['method'] == 'GET' for c in values('ro'))
    proof['rights']['ro'] = {'lookup': True, 'mutation_blocked_without_provider_call': True}
    # Write-only never reads keys or values; the local write result is sufficient for delete.
    _, wo = opened('wo')
    command(wo, 'n'); literal(wo, 'string'); literal(wo, 'blind'); literal(wo, 'known')
    wait_for(lambda: instance.get('blind') == 'known')
    command(wo, 'd'); literal(wo, 'yes')
    wait_for(lambda: 'blind' not in list(instance.keys()))
    assert [c['method'] for c in values('wo')] == ['PUT', 'DELETE']
    assert all(c['path'].endswith('/connect') or c['method'] != 'GET' for c in calls('wo'))
    proof['rights']['wo'] = {'write_then_delete': True, 'keys_get_or_read_before_write': False}
    # Context key/Instance collision stays separated in the installed Child navigation.
    _, context_pane = opened('context')
    keys(context_pane, 'Enter')  # values
    wait_for(lambda: 'text' in screen(context_pane))
    choose(context_pane, 'same', owner.keys()); keys(context_pane, 'Enter')
    wait_for(lambda: 'context conflict' in screen(context_pane))
    keys(context_pane, 'z', 'U'); keys(context_pane, 'Down', 'Enter')  # instances
    wait_for(lambda: 'same' in screen(context_pane))
    keys(context_pane, 'Enter')
    wait_for(lambda: 'text' in screen(context_pane))
    choose(context_pane, 'same', names); keys(context_pane, 'Enter')
    wait_for(lambda: 'instance conflict' in screen(context_pane))
    proof['collision'] = True
    # A real target-side auth failure leaves the same process/window and confirmed row alive.
    tmux(sock, 'select-window', '-t', result['window_id'])
    tmux(sock, 'select-pane', '-t', pane)
    owner.token_delete(token_id='rw')
    choose(pane, 'text', names); keys(pane, 'l', 'l', 'Enter'); literal(pane, 'forbidden')
    wait_for(lambda: 'Error' in screen(pane))
    assert instance.get('text') == long
    assert tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead}') == '0'
    assert not any(secret in screen(pane) for secret in secrets)
    assert 'complete clipboard $text;' in screen(pane)
    proof['provider_error_preserves_window'] = True
    # Only the intended text value changed; context values and all complex values survive.
    final = instance.state()
    assert final == {**initial, 'same': 'instance conflict', 'text': long}
    assert owner.snapshot()['context']['state'] == initial
    meta = tmux(sock, 'show-environment', '-t', 'a') + tmux(sock, 'show-options', '-w', '-t', result['window_id'])
    meta += tmux(sock, 'list-panes', '-t', result['window_id'], '-F', '#{pane_start_command} #{pane_title}')
    assert not any(secret in meta for secret in secrets)
    for role in result['panes'].values():
        pid = int(tmux(sock, 'display-message', '-p', '-t', role['pane_id'], '#{pane_pid}'))
        pending = [pid]
        while pending:
            current = pending.pop()
            try:
                process = Path('/proc') / str(current)
                material = (process / 'cmdline').read_bytes() + (process / 'environ').read_bytes()
                assert not any(secret.encode() in material for secret in secrets)
                pending.extend(map(int, (process / 'task' / str(current) / 'children').read_text().split()))
            except FileNotFoundError:
                pass
    destination = os.environ.get('DIX_NOLSPACE_EVIDENCE_DIR')
    if destination:
        out = Path(destination); out.mkdir(parents=True, exist_ok=True)
        (out / 'installed-nolspace-proof.json').write_text(json.dumps(proof, indent=2) + '\n')
        for name in ('rw', 'ro', 'wo', 'context'):
            (out / (name + '-endpoints.json')).write_text(json.dumps(calls(name), indent=2) + '\n')
