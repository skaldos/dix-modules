from __future__ import annotations

import fcntl
import json
import os
import pty
import shlex
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest
from test_cockpit_store_workspace import drain_terminal, tmux, wait_for


@pytest.fixture(params=['catalog', 'types'])
def terminal_store(request, store_graph):
    create, _, root = store_graph
    workspace = create('skaldos/cockpit/cockpit_session').api
    started = workspace.require('start')(session='a', shell_command=['sleep', '300'],
                                        status_command=['sleep', '300'], attach=False)
    sock = started['tmux']['socket']
    source = Path(__file__).parents[1]
    evidence = root / 'keys.json'
    command = [sys.executable, str(source / 'tests/probes/store_workbench_probe.py'),
               str(source), str(evidence), request.param]
    pane = tmux(sock, 'new-window', '-d', '-t', 'a', '-n', 'keys', '-P', '-F', '#{pane_id}',
                'env PYTHONPATH=' + shlex.quote(str(Path(os.environ.get(
                    'DIX_REPOSITORY', '/cwd/repos/dix')) / 'src')) + ' ' + shlex.join(command))
    tmux(sock, 'set-option', '-p', '-t', pane, 'remain-on-exit', 'on')
    tmux(sock, 'select-window', '-t', 'a:keys')
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 45, 160, 0, 0))
    process = subprocess.Popen(['tmux', '-S', sock, 'attach-session', '-t', 'a'],
                               stdin=slave, stdout=slave, stderr=slave,
                               env={**os.environ, 'TERM': 'xterm-256color', 'TMUX': ''})
    os.close(slave)
    drain_terminal(master)

    class Terminal:
        mode = request.param
        def __init__(self):
            self.trace = []

        def state(self):
            return json.loads(evidence.read_text())

        def wait(self, predicate):
            wait_for(lambda: evidence.exists() and predicate(self.state()))

        def keys(self, *keys):
            tmux(sock, 'send-keys', '-t', pane, *keys)
            time.sleep(.12)
            if evidence.exists():
                self.trace.append({'keys': list(keys), 'state': self.state()})

        def screen(self):
            return tmux(sock, 'capture-pane', '-p', '-t', pane)

        def edit(self, text, cancel=False):
            self.keys('Enter')
            self.wait(lambda s: s['editing'])
            tmux(sock, 'send-keys', '-t', pane, '-l', text)
            self.keys('Escape' if cancel else 'Enter')
            self.wait(lambda s: not s['editing'])
            time.sleep(.1)

        def guard(self, key, decision):
            self.keys(*key)
            wait_for(lambda: 'Save / Discard / Cancel' in self.screen())
            self.keys(decision, 'Enter')

    terminal = Terminal()
    terminal.backend = lambda: create('skaldos/cockpit/store_catalog').api.require('list')('a')
    try:
        terminal.wait(lambda s: s['draft'] is None)
        # The unchanged external VisiData distribution can show a first-run splash.
        time.sleep(.4)
        if 'Press Enter' in terminal.screen():
            terminal.keys('Enter')
        wait_for(lambda: 'Stores' in terminal.screen())
        yield terminal
        assert terminal.state()['metrics']['target_transport'] == 0
    finally:
        tmux(sock, 'detach-client', '-s', 'a')
        process.wait(timeout=5)
        os.close(master)
        destination = os.environ.get('DIX_STORE_KEYS_EVIDENCE_DIR')
        if destination and evidence.exists():
            target = Path(destination)
            target.mkdir(parents=True, exist_ok=True)
            decision = request.node.callspec.params.get('decision')
            stem = request.param if decision is None else f'native-{request.param}-{decision}'
            (target / (stem + '-final.json')).write_text(evidence.read_text())
            (target / (stem + '-keys.json')).write_text(json.dumps(terminal.trace, indent=2))
        workspace.require('stop')(session='a')


def test_real_native_inline_enter_escape_types_save_and_guards(terminal_store):
    t = terminal_store
    t.keys('q')
    assert t.state()['draft'] is None
    t.keys('a')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('local-store')
    t.wait(lambda s: s['dirty'])
    assert t.state()['entries'] == [] and t.state()['metrics']['create'] == 0
    assert 'DIRTY' in t.screen()
    if t.mode == 'catalog':
        assert t.backend() == []
    t.edit('cancelled-name', cancel=True)
    assert t.state()['draft']['store_id'] == 'local-store'
    t.keys('Down', 'Down', 'Enter')
    t.wait(lambda s: s['path'] == ['connection'])
    if t.mode == 'catalog':
        for text in ('offline', 'unix:/tmp/no-target.sock', 'synthetic-draft'):
            t.edit(text)
            t.keys('Down')
    else:
        t.edit('without quotes')
        t.keys('Down')
        t.edit('42')
        assert type(t.state()['draft']['connection']['count']) is int
        t.keys('Down')
    t.edit('not-a-number')
    assert t.state()['draft']['connection']['timeout'] == 5.0
    t.edit('1.25')
    assert type(t.state()['draft']['connection']['timeout']) is float
    if t.mode == 'types':
        t.keys('Down')
        t.edit('false')
        assert t.state()['draft']['connection']['enabled'] is False, (t.state(), t.screen())
        t.edit('not-bool')
        assert t.state()['draft']['connection']['enabled'] is False, (t.state(), t.screen())
        t.keys('Down', 'Enter')
        t.wait(lambda s: s['path'] == ['connection', 'nested'])
        t.edit('3')
        t.keys('q')
        t.wait(lambda s: s['path'] == ['connection'])
    t.keys('q')  # Internal parent does not ask and does not discard.
    t.wait(lambda s: s['path'] == [])
    t.guard(('q',), 'c')
    assert t.state()['dirty']
    t.keys('z', 'C-s')
    t.wait(lambda s: not s['dirty'])
    assert t.state()['metrics'] == {'create': 1, 'update': 0, 'success': 1, 'target_transport': 0}
    assert len(t.state()['entries']) == 1
    if t.mode == 'catalog':
        backend = t.backend()
        assert backend[0]['connection']['context_locator'] == 'unix:/tmp/no-target.sock'
        assert backend[0]['connection']['timeout'] == 1.25
        assert backend[0]['connection']['token'] == 'synthetic-draft'
    # Existing draft: Cancel, Discard, Save are distinct, with no per-cell writes.
    t.keys('Home')
    t.edit('discarded-rename')
    t.guard(('q',), 'c')
    assert t.state()['dirty']
    t.guard(('q',), 'd')
    t.wait(lambda s: s['draft'] is None)
    assert t.state()['entries'][0]['store_id'] == 'local-store'
    t.keys('Enter')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('saved-rename')
    t.guard(('q',), 's')
    t.wait(lambda s: s['draft'] is None)
    assert t.state()['metrics']['update'] == 1 and t.state()['metrics']['success'] == 2
    assert t.state()['entries'][0]['store_id'] == 'saved-rename'
    # New dirty draft: invalid commit preserves dirty, Cancel preserves, Discard writes nothing.
    t.keys('a')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('invalid-new')
    t.guard(('q',), 's')
    assert t.state()['dirty'] and t.state()['error']
    assert t.state()['metrics']['success'] == 2
    t.guard(('C-r',), 'c')
    assert t.state()['dirty']
    t.guard(('a',), 'c')
    assert t.state()['draft']['store_id'] == 'invalid-new'
    t.guard(('g', 'q'), 'c')
    assert not t.state()['exit']
    t.guard(('Q',), 'd')
    t.wait(lambda s: s['draft'] is None)
    assert len(t.state()['entries']) == 1
    t.keys('q')
    assert not t.state()['exit']
    # Successful guarded Save for an existing draft through Reload.
    t.keys('Enter')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('saved-by-reload')
    t.guard(('C-r',), 's')
    t.wait(lambda s: s['draft'] is None)
    assert t.state()['metrics']['update'] == 2
    # Successful guarded Save for a new draft, then guarded Discard on explicit exit.
    t.keys('a')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('new-via-guard')
    if t.mode == 'catalog':
        t.keys('Down', 'Down', 'Enter')
        t.wait(lambda s: s['path'] == ['connection'])
        for text in ('offline', 'unix:/tmp/no-target.sock', 'synthetic-draft'):
            t.edit(text)
            t.keys('Down')
        t.keys('q')
        t.wait(lambda s: s['path'] == [])
    t.guard(('q',), 's')
    t.wait(lambda s: s['draft'] is None)
    assert t.state()['metrics']['success'] == 4
    if t.mode == 'catalog':
        assert {r['store_id'] for r in t.backend()} == {'saved-by-reload', 'new-via-guard'}
    t.keys('a')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('discard-on-exit')
    t.guard(('g', 'q'), 'd')
    t.wait(lambda s: s['exit'])


@pytest.mark.parametrize('decision', ['s', 'd'])
def test_native_exit_is_guarded_by_local_runtime(terminal_store, decision):
    t = terminal_store
    t.keys('a')
    t.wait(lambda s: s['draft'] is not None)
    t.edit('invalid-new')
    cursor = t.state()['cursor']
    t.guard(('C-q',), 'c')
    assert t.state()['cursor'] == cursor
    assert t.state()['dirty'] and not t.state()['exit']
    t.guard(('C-q',), 's')  # Invalid save must return to the same native Sheet.
    t.wait(lambda s: bool(s['error']))
    assert t.state()['dirty'] and not t.state()['exit']
    assert t.state()['metrics']['success'] == 0
    t.edit('native-exit-save')
    if t.mode == 'catalog':
        t.keys('Down', 'Down', 'Enter')
        t.wait(lambda s: s['path'] == ['connection'])
        for text in ('offline', 'unix:/tmp/no-target.sock', 'synthetic-draft'):
            t.edit(text)
            t.keys('Down')
        t.keys('q')
        t.wait(lambda s: s['path'] == [])
    # Native auxiliary Sheet uses its original global quit; the owning runtime still guards.
    t.keys('z', 'F1')
    wait_for(lambda: 'longname' in t.screen())
    t.keys('g', 'q')
    wait_for(lambda: 'Dirty Store after native exit' in t.screen())
    t.keys('c', 'Enter')
    assert t.state()['dirty'] and not t.state()['exit']
    t.guard(('C-q',), decision)
    t.wait(lambda s: s['exit'])
    expected = 1 if decision == 's' else 0
    assert t.state()['metrics']['success'] == expected
    if t.mode == 'catalog':
        assert len(t.backend()) == expected
