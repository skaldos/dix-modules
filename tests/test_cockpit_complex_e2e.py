from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path

from roba import RobaClient
from test_cockpit_clipboard import _tool
from test_cockpit_nolspace_e2e import installed_ui as installed_ui  # noqa: PLC0414
from test_cockpit_nolspace_e2e import nolspace_client as nolspace_client  # noqa: PLC0414
from test_cockpit_nolspace_e2e import real_owned_ui as real_owned_ui  # noqa: PLC0414
from test_cockpit_store_workspace import tmux, wait_for

ROOT = Path(__file__).parents[1]


def test_installed_complex_root_edits_and_failed_system_clipboard(nolspace_client):
    installed, client = nolspace_client
    create, workspace, _, started, binary, launchers, root = installed
    assert (launchers / 'cockpit/clipboard.py').read_bytes() == (ROOT / 'cockpit/integrations/clipboard.py').read_bytes()
    runtime = create('skaldos/cockpit/roba_runtime').api
    env = runtime.require('owner_environment')(session='b')
    context = RobaClient(env=env).control().context_create(context_id='n69')
    owner = RobaClient(env={}).context(locator='unix:' + context['socket'], token=context['owner_token'])
    initial = {'complex': {'title': 'original', 'items': [1, False, {'nested': 'before'}]},
               'array': [7, {'enabled': True}, ['deep']],
               'long': 'literal $HOME;$(touch impossible)\n' + 'z' * 5000 + '\nlast line'}
    for key, value in initial.items(): owner.set(key, value)
    owner.instance_create(instance_id='complex-instance', state={'complex': {'count': 8}})
    reader = owner.token_create(token_id='reader', read=['context', 'instance:complex-instance'])['token']
    rw = owner.token_create(token_id='rw', read=['context'], write=['context'])['token']
    catalog = create('skaldos/cockpit/store_browser').runtime.catalog
    base = {'context_id': 'n69', 'context_locator': 'unix:' + context['socket'], 'timeout': 2.0}
    for name, token, scoped in [('complex-rw', rw, {}), ('complex-ro', reader, {}),
                                ('complex-instance', context['owner_token'], {'instance_id': 'complex-instance'})]:
        catalog.require('create')({'store_id': name, 'provider': 'roba',
                                  'connection': {**base, 'token': token, **scoped}}, 'a')
    trace = root / 'trace'; trace.mkdir()
    wrapper = binary / 'dix-cockpit-store-browser'
    wrapper.write_text(wrapper.read_text().replace('"$DIX_LAUNCHERS/dix-cockpit-store-browser.py"',
        shlex.quote(str(ROOT / 'tests/probes/nolspace_installed_probe.py')) + ' ' +
        '"$DIX_LAUNCHERS/dix-cockpit-store-browser.py" ' + shlex.quote(str(trace))))
    tools = root / 'broken-clipboard'; tools.mkdir()
    marker = root / 'system-attempts'
    _tool(tools, 'wl-copy', f'echo copy >> {shlex.quote(str(marker))}; cat >/dev/null; exit 19')
    _tool(tools, 'wl-paste', f'echo paste >> {shlex.quote(str(marker))}; printf partial-must-not-mix; exit 19')
    sock = started['tmux']['socket']
    # Installed wrappers remain real; inject only a deliberately broken system backend.
    # tmux may reset PATH/update-environment for newly spawned windows.
    for mode in ('copy', 'paste'):
        adapter = binary / ('dix-cockpit-clipboard-' + mode)
        adapter.write_text(adapter.read_text().replace('set -eu\n', 'set -eu\nexport WAYLAND_DISPLAY=unavailable\nexport PATH=' +
                           shlex.quote(str(tools) + ':' + os.environ['PATH']) + '\n', 1))
    def screen(pane): return tmux(sock, 'capture-pane', '-p', '-t', pane)
    def keys(pane, *values):
        tmux(sock, 'send-keys', '-t', pane, *values); time.sleep(.15)
    def literal(pane, value):
        tmux(sock, 'send-keys', '-t', pane, '-l', '--', value); keys(pane, 'Enter')
    def choose(pane, index, column=0):
        keys(pane, 'h', 'h', 'g', 'g')
        for _ in range(index): keys(pane, 'j')
        for _ in range(column): keys(pane, 'l')
    def calls(name):
        path = trace / (name + '.jsonl')
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    def values(name): return [c for c in calls(name) if '/state/' in c['path']]
    def open_store(name):
        result = workspace.require('open_store')(store_id=name, revision=catalog.require('record')(name, 'a')['revision'], session='a')
        pane = result['panes']['browser']['pane_id']
        wait_for(lambda: 'Nolspace' in screen(pane))
        wait_for(lambda: ('complex' if name == 'complex-instance' else 'instances') in screen(pane))
        if name != 'complex-instance': keys(pane, 'Enter')
        return result, pane
    result, pane = open_store('complex-rw')
    assert values('complex-rw') == []
    names = owner.keys()
    # Unloaded Enter in type performs lookup once, not an edit on the same keypress.
    choose(pane, names.index('complex'), 1); keys(pane, 'Enter')
    wait_for(lambda: len(values('complex-rw')) == 1)
    assert values('complex-rw')[0]['method'] == 'GET'
    keys(pane, 'Enter')  # local object
    choose(pane, 1); keys(pane, 'Enter')  # items
    choose(pane, 0, 2); keys(pane, 'Enter'); literal(pane, 'not-an-integer')
    wait_for(lambda: 'valid integer' in screen(pane))
    assert len(values('complex-rw')) == 1 and owner.get('complex') == initial['complex']
    keys(pane, 'Enter'); keys(pane, 'Escape'); time.sleep(.4)
    assert 'valid integer' not in screen(pane)
    assert len(values('complex-rw')) == 1
    keys(pane, 'Enter'); literal(pane, '42')
    wait_for(lambda: owner.get('complex')['items'][0] == 42)
    choose(pane, 1, 2); keys(pane, 'Enter'); literal(pane, 'true')
    choose(pane, 2); keys(pane, 'Enter'); choose(pane, 0, 2); keys(pane, 'Enter'); literal(pane, 'after')
    expected = {'title': 'original', 'items': [42, True, {'nested': 'after'}]}
    wait_for(lambda: owner.get('complex') == expected)
    assert [c['method'] for c in values('complex-rw')] == ['GET', 'PUT', 'PUT', 'PUT']
    assert all(c['path'].endswith('/state/complex') for c in values('complex-rw'))
    # Structural mutation remains blocked. A successful local parent clears that error.
    keys(pane, ':'); literal(pane, 'n')
    wait_for(lambda: 'structure is read-only' in screen(pane))
    keys(pane, 'q'); wait_for(lambda: 'structure is read-only' not in screen(pane))
    keys(pane, 'q', 'q')
    # Unloaded value Enter is also load-only; navigation and y never fetch it implicitly.
    choose(pane, names.index('long'), 2); before = len(values('complex-rw'))
    keys(pane, 'y'); wait_for(lambda: 'not loaded' in screen(pane))
    assert len(values('complex-rw')) == before
    keys(pane, 'Enter'); wait_for(lambda: 'not loaded' not in screen(pane))
    keys(pane, 'y'); wait_for(lambda: tmux(sock, 'save-buffer', '-') == initial['long'])
    assert len(values('complex-rw')) == before + 1
    assert marker.read_text().splitlines() == ['copy']
    # Real client prefix paste into the owned shell with a failing system paste backend.
    captured = root / 'pasted-bytes'
    command = (f"import os; from pathlib import Path; p=Path({str(captured)!r}); data=b''\n"
               f"while len(data) < {len(initial['long'].encode())}: data += os.read(0, 20000)\n"
               "p.write_bytes(data)")
    ready = root / 'paste-ready'
    shell = tmux(sock, 'new-window', '-t', 'a', '-P', '-F', '#{pane_id}',
        'stty -icanon -echo; touch ' + shlex.quote(str(ready)) + '; ' + shlex.quote(os.sys.executable) + ' -c ' + shlex.quote(command) + '; sleep 300')
    wait_for(ready.exists)
    tmux(sock, 'select-pane', '-t', shell)
    os.write(client, b'\x01p')
    wait_for(captured.exists)
    assert captured.read_bytes() == initial['long'].encode()
    assert marker.read_text().splitlines() == ['copy', 'paste']
    # Native Instance root replacement, distinct from the context key.
    _, inst = open_store('complex-instance')
    choose(inst, 0, 2); keys(inst, 'Enter', 'Enter'); choose(inst, 0, 2); keys(inst, 'Enter'); literal(inst, '9')
    wait_for(lambda: owner.with_scope('id:complex-instance').get('complex') == {'count': 9})
    assert [c['method'] for c in values('complex-instance')] == ['GET', 'PUT']
    # Reader follows the same local projection but cannot open an editor or issue a write.
    _, ro = open_store('complex-ro')
    choose(ro, names.index('complex'), 0); keys(ro, 'Enter', 'Enter')
    choose(ro, 1); keys(ro, 'Enter'); choose(ro, 0, 2); keys(ro, 'Enter')
    wait_for(lambda: 'does not offer upsert' in screen(ro))
    assert [c['method'] for c in values('complex-ro')] == ['GET']
    keys(ro, 'q'); wait_for(lambda: 'does not offer' not in screen(ro))
    # Reopen focuses the existing definition/revision window; no extra target read.
    reopened = workspace.require('open_store')(store_id='complex-rw', revision=catalog.require('record')('complex-rw', 'a')['revision'], session='a')
    assert reopened['window_id'] == result['window_id']
    assert owner.state() == {**initial, 'complex': expected}
    secrets = [context['owner_token'], reader, rw, env['ROBA_CONTROL_TOKEN']]
    meta = tmux(sock, 'show-environment', '-t', 'a') + tmux(sock, 'show-options', '-w', '-t', result['window_id'])
    meta += tmux(sock, 'list-panes', '-t', result['window_id'], '-F', '#{pane_start_command} #{pane_title}')
    assert not any(secret in meta for secret in secrets)
    assert tmux(sock, 'display-message', '-p', '-t', pane, '#{pane_dead}') == '0'
    destination = os.environ.get('DIX_COMPLEX_EVIDENCE_DIR')
    if destination:
        target = Path(destination); target.mkdir(parents=True, exist_ok=True)
        (target / 'complex-proof.json').write_text(json.dumps({
            'context_root_methods': [c['method'] for c in values('complex-rw') if c['path'].endswith('/state/complex')],
            'instance_root_methods': [c['method'] for c in values('complex-instance')],
            'reader_methods': [c['method'] for c in values('complex-ro')],
            'system_failures': marker.read_text().splitlines(), 'clipboard_exact_bytes': len(initial['long'].encode()),
            'sibling_preservation': True, 'canonical_cache': True, 'old_error_cleared': True,
            'same_window_reopened': True, 'secret_transport': False,
        }, indent=2) + '\n')
        for name in ('complex-rw', 'complex-ro', 'complex-instance'):
            (target / (name + '-endpoints.json')).write_text(json.dumps(calls(name), indent=2) + '\n')
