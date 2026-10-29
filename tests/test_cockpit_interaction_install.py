from __future__ import annotations

import fcntl
import json
import os
import pty
import shlex
import socket
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest
from test_cockpit_store_workspace import drain_terminal, tmux, wait_for

ROOT = Path(__file__).parents[1]


@pytest.fixture
def installed_ui(store_graph, tmp_path, monkeypatch):
    create, _, root = store_graph
    dix = Path(os.environ.get('DIX_REPOSITORY', '/cwd/repos/dix'))
    python = Path(os.environ.get('DIX_PYTHON', sys.executable))
    monkeypatch.setenv('PYTHONPATH', str(dix / 'src'))
    venv, launchers, binary, tools = (tmp_path / x for x in ('v', 'l', 'b', 't'))
    (venv / 'bin').mkdir(parents=True)
    tools.mkdir()
    (tools / 'uv').write_text('#!/bin/sh\nexit 0\n')
    (tools / 'uv').chmod(0o755)
    (tools / 'chafa').write_text('#!/bin/sh\nprintf "BRANDING_PROBE\\n"\n')
    (tools / 'chafa').chmod(0o755)
    (venv / 'bin/python').write_text(f'#!/bin/sh\nexec "{python}" "$@"\n')
    (venv / 'bin/python').chmod(0o755)
    env = tmp_path / 'env'
    env.write_text('\n'.join(f'export {k}={shlex.quote(str(v))}' for k, v in {
        'DIX_SOURCE_ROOT': dix, 'DIX_VENV': venv, 'DIX_LAUNCHERS': launchers,
        'DIX_BIN': binary, 'DIX_ENV': env}.items())+'\n')
    monkeypatch.setenv('DIX_ENV', str(env))
    monkeypatch.setenv('DIX_BIN', str(binary))
    monkeypatch.setenv('PATH', f"{tools}:{os.environ['PATH']}")
    for name in ('install', 'install-ui', 'install-workbench'):
        proc = subprocess.run([str(ROOT / 'cockpit/integrations' / name)],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
    workspace = create('skaldos/cockpit/cockpit_session').api
    args = {'session': 'a', 'shell_command': ['sleep', '300'],
            'status_command': ['sleep', '300'], 'attach': False,
            'workbench_command': [str(binary / 'dix-cockpit-master-workbench'), '--session', 'a'],
            'store_command': [str(binary / 'dix-cockpit-store-workbench'), '--session', 'a']}
    result = workspace.require('start_master')(**args)
    sock = result['tmux']['socket']
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 45, 160, 0, 0))
    client = subprocess.Popen(['tmux', '-S', sock, 'attach-session', '-t', 'a'],
                              stdin=slave, stdout=slave, stderr=slave,
                              env={**os.environ, 'TERM': 'xterm-256color', 'TMUX': ''})
    os.close(slave)
    drain_terminal(master)
    try:
        yield create, workspace, args, result, binary, launchers, root
    finally:
        tmux(sock, 'detach-client', '-s', 'a')
        client.wait(timeout=5)
        os.close(master)
        workspace.require('stop')(session='a')


def test_real_installed_store_and_direct_master_without_enter(installed_ui):
    create, workspace, args, result, _, _, root = installed_ui
    sock = result['tmux']['socket']
    store, master = result['store']['pane_id'], result['workbench']['pane_id']
    catalog = create('skaldos/cockpit/store_catalog').api
    wait_for(lambda: 'connection' in tmux(sock, 'capture-pane', '-p', '-t', master))
    assert 'Press Enter' not in tmux(sock, 'capture-pane', '-p', '-t', master)
    wait_for(lambda: 'Stores' in tmux(sock, 'capture-pane', '-p', '-t', store))
    assert 'File  Edit  View' not in tmux(sock, 'capture-pane', '-p', '-t', store)

    trace = []

    def keys(*data):
        trace.append({'keys': list(data)})
        tmux(sock, 'send-keys', '-t', store, *data)
        time.sleep(.2)

    def command(token):
        trace.append({'prompt': token})
        keys(':')
        keys(token, 'Enter')

    def edit(text):
        trace.append({'edit': text})
        keys('Enter')
        tmux(sock, 'send-keys', '-t', store, '-l', text)
        keys('Enter')

    target = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    target.bind(str(root / 'target.sock'))
    target.listen()
    target.setblocking(False)
    try:
        command('n')
        wait_for(lambda: 'store_id' in tmux(sock, 'capture-pane', '-p', '-t', store))
        edit('installed')
        keys('Down', 'Down', 'Enter')
        edit('offline'); keys('Down')
        edit('unix:' + str(root / 'target.sock')); keys('Down')
        edit('synthetic-installed'); keys('Down')
        edit('0.75'); keys('q')
        command('w')
        wait_for(lambda: len(catalog.require('list')('a')) == 1)
        assert catalog.require('list')('a')[0]['connection']['timeout'] == .75
        keys('g', 'g'); edit('saved-by-wq')
        for data in (('i',), ('-',), ('a',), ('z', 'C-s'), ('g', 'q'), ('C-f',)):
            keys(*data)
        command('unknown')
        wait_for(lambda: 'Unknown Cockpit' in tmux(sock, 'capture-pane', '-p', '-t', store))
        command('wq')
        wait_for(lambda: tmux(sock, 'display-message', '-p', '-t', store, '#{pane_dead}') == '1')
        assert catalog.require('list')('a')[0]['store_id'] == 'saved-by-wq'
        again = workspace.require('start_master')(**args)
        assert again['store'] == {'pane_id': store, 'action': 'respawned'}
        wait_for(lambda: 'saved-by-wq' in tmux(sock, 'capture-pane', '-p', '-t', store))
        keys('q')
        assert tmux(sock, 'display-message', '-p', '-t', store, '#{pane_dead}') == '0'
        keys('C-r')  # Direct Reload alias, no draft yet.
        command('n'); edit('invalid')
        keys('Enter')
        tmux(sock, 'send-keys', '-t', store, '-l', 'cancelled-cell')
        keys('Escape')
        time.sleep(1.1)  # Native terminal ESC disambiguation must finish before Ctrl+R.
        assert 'invalid' in tmux(sock, 'capture-pane', '-p', '-t', store)
        for route in ('reload', 'n', 'q'):
            keys('C-r') if route == 'reload' else command(route)
            try:
                wait_for(lambda: 'Save / Discard / Cancel' in tmux(sock, 'capture-pane', '-p', '-t', store))
            except AssertionError:
                raise AssertionError(f'guard {route}: ' + tmux(sock, 'capture-pane', '-p', '-t', store)) from None
            keys('c', 'Enter')
        keys('C-q')
        wait_for(lambda: 'Dirty Store after native exit' in tmux(sock, 'capture-pane', '-p', '-t', store))
        keys('c', 'Enter')
        wait_for(lambda: 'invalid' in tmux(sock, 'capture-pane', '-p', '-t', store))
        keys('C-s')  # Invalid whole-draft Save must leave the installed process alive.
        command('wq')
        assert tmux(sock, 'display-message', '-p', '-t', store, '#{pane_dead}') == '0'
        command('q!')
        wait_for(lambda: tmux(sock, 'display-message', '-p', '-t', store, '#{pane_dead}') == '1')
        assert len(catalog.require('list')('a')) == 1
        with pytest.raises(BlockingIOError):
            target.accept()
        destination = os.environ.get('DIX_INTERACTION_EVIDENCE_DIR')
        if destination:
            out = Path(destination)
            out.mkdir(parents=True, exist_ok=True)
            (out / 'installed-master-store.json').write_text(json.dumps({
                'master_without_enter': True, 'store_respawned_same_pane': True,
                'local_catalog': catalog.require('list')('a'), 'target_connections': 0,
                'native_quit_cancel_resumed': True, 'keys': trace}, indent=2))
    finally:
        target.close()


@pytest.mark.parametrize('mode', ['bad-version', 'bad-registry', 'generic', 'toml'])
def test_installed_gate_failures_and_other_workbench_defaults(installed_ui, mode):
    _, _, _, result, _, launchers, root = installed_ui
    sock = result['tmux']['socket']
    evidence = root / (mode + '.json')
    if mode == 'generic':
        target = launchers / 'cockpit/master-ui-modules/visidata'
    elif mode == 'toml':
        target = launchers / 'dix-cockpit-toml-workbench.py'
    else:
        target = launchers / 'dix-cockpit-store-workbench.py'
    command = [sys.executable, str(ROOT / 'tests/probes/interaction_start_probe.py'),
               mode, str(target), str(evidence)]
    if mode == 'toml':
        file = root / 'example.toml'
        file.write_text('[project]\nname = "practical"\n')
        command.append(str(file))
    pane = tmux(sock, 'new-window', '-d', '-t', 'a', '-n', 'probe', '-P', '-F', '#{pane_id}',
                shlex.join(command) if not mode.startswith('bad-') else
                shlex.join(['sh', '-c', shlex.join(command) + '; code=$?; sleep 2; exit "$code"']))
    tmux(sock, 'set-option', '-p', '-t', pane, 'remain-on-exit', 'on')
    tmux(sock, 'select-window', '-t', 'a:probe')
    screen = lambda: tmux(sock, 'capture-pane', '-p', '-S', '-', '-t', pane)
    if mode.startswith('bad-'):
        wait_for(lambda: tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead}') == '1')
        assert 'Cockpit Store requires VisiData 3.4' in screen()
        assert 'UNEXPECTED_CURSES' not in screen() and 'Traceback' not in screen()
        assert tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead_status}') == '2'
    else:
        wait_for(lambda: 'Press Enter for VisiData' in screen())
        assert 'BRANDING_PROBE' in screen()
        tmux(sock, 'send-keys', '-t', pane, 'Enter')
        wait_for(lambda: evidence.exists())
        proof = json.loads(evidence.read_text())
        assert len(proof['after']) > 17 and all(proof['defaults'].values())
        for key, scopes in proof['before'].items():
            for context, value in scopes.items():
                assert proof['after'].get(key, {}).get(context) == value
        tmux(sock, 'send-keys', '-t', pane, 'C-q')
        wait_for(lambda: tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead}') == '1')
    destination = os.environ.get('DIX_INTERACTION_EVIDENCE_DIR')
    if destination:
        out = Path(destination)
        out.mkdir(parents=True, exist_ok=True)
        (out / (mode + '.txt')).write_text(screen())
        if evidence.exists():
            (out / (mode + '.json')).write_text(evidence.read_text())
