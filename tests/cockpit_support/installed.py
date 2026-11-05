from __future__ import annotations

import fcntl
import os
import pty
import shlex
import struct
import subprocess
import sys
import termios
from pathlib import Path

import pytest

from .terminal import drain_terminal, tmux

ROOT = Path(__file__).parents[2]



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



@pytest.fixture
def real_owned_ui(request, store_graph):
    # Start the native target daemon before attaching a PTY drain thread.
    _create, runtime, _ = store_graph
    runtime.require('start')(session='b')
    return request.getfixturevalue('installed_ui')



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

