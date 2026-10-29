from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_cockpit_store_workspace import tmux, wait_for


def workspace(store_graph):
    create, _, root = store_graph
    session = create('skaldos/cockpit/cockpit_session').api
    started = session.require('start')(
        session='a', shell_command=['sleep','300'], status_command=['sleep','300'], attach=False)
    bound = create('skaldos/cockpit/tmux_workspace')
    args = {'session':'a', 'socket':started['tmux']['socket'], 'store_id':'project alpha',
            'revision':'a'*32, 'commands':{'status':['sleep','300'], 'browser':['sleep','300']}}
    return bound, args, root


def test_owned_store_window_lifecycle_focus_repair_rename_move_revision_recreate(store_graph):
    bound, args, _ = workspace(store_graph)
    api, sock = bound.api, args['socket']
    first = api.require('open_store')(**args)
    window = first['window_id']
    status, browser = [first['panes'][key]['pane_id'] for key in ('status','browser')]
    pid = lambda pane: tmux(sock, 'display-message','-p','-t',pane,'#{pane_pid}')
    pids = [pid(status),pid(browser)]
    again = api.require('open_store')(**args)
    assert again['window_id'] == window and again['action'] == 'focused'
    assert [pid(status),pid(browser)] == pids
    assert len(tmux(sock,'list-panes','-t',window).splitlines()) == 2
    assert tmux(sock,'display-message','-p','#{window_id} #{pane_id}') == f'{window} {browser}'
    tmux(sock,'rename-window','-t',window,'renamed by owner')
    tmux(sock,'move-window','-s',window,'-t','a:9')
    assert api.require('open_store')(**args)['window_id'] == window
    assert tmux(sock,'display-message','-p','-t',window,'#{window_index}') == '9'
    for key, other in (('browser','status'),('status','browser')):
        pane = again['panes'][key]['pane_id']; healthy = again['panes'][other]['pane_id']
        healthy_pid = pid(healthy)
        tmux(sock,'respawn-pane','-k','-t',pane,'true')
        wait_for(lambda pane=pane: tmux(sock,'display-message','-p','-t',pane,'#{pane_dead}') == '1')
        repaired = api.require('open_store')(**args)
        assert repaired['panes'][key] == {'pane_id':pane,'action':'respawned'}
        assert pid(healthy) == healthy_pid
        tmux(sock,'kill-pane','-t',pane)
        again = api.require('open_store')(**args)
        assert again['panes'][key]['action'] == 'created'
        assert pid(healthy) == healthy_pid
    status, browser = [again['panes'][key]['pane_id'] for key in ('status','browser')]
    pids = [pid(status),pid(browser)]
    args['revision'] = 'b'*32
    rebuilt = api.require('open_store')(**args)
    assert rebuilt['action'] == 'rebuilt' and rebuilt['window_id'] == window
    assert [pid(status),pid(browser)] != pids
    assert all(pid(pane) != old for pane, old in zip((status,browser),pids))
    assert tmux(sock,'show-option','-w','-v','-t',window,'@cockpit-store-revision') == 'b'*32
    tmux(sock,'kill-window','-t',window)
    recreated = api.require('open_store')(**args)
    assert recreated['action'] == 'created' and recreated['window_id'] != window


@pytest.mark.parametrize('damage', ['foreign-pane','duplicate-pane','wrong-store','wrong-revision',
                                   'wrong-session','foreign-window','duplicate-window','missing-revision'])
def test_store_workspace_metadata_failures_never_adopt_or_delete(store_graph, damage):
    bound, args, _ = workspace(store_graph)
    first = bound.api.require('open_store')(**args)
    sock, window = args['socket'],first['window_id']
    browser = first['panes']['browser']['pane_id']
    if damage in ('foreign-pane','duplicate-pane'):
        role = 'foreign.owner' if damage=='foreign-pane' else 'skaldos.dix-cockpit.store-status.v1'
        tmux(sock,'set-option','-p','-t',browser,'@cockpit-pane-role',role)
    elif damage.startswith('wrong-'):
        key = {'wrong-store':'id','wrong-revision':'revision','wrong-session':'session'}[damage]
        tmux(sock,'set-option','-p','-t',browser,'@cockpit-view-store-'+key,'wrong')
    elif damage=='foreign-window':
        tmux(sock,'set-option','-w','-t',window,'@cockpit-window-role','foreign.owner')
    elif damage=='missing-revision':
        tmux(sock,'set-option','-w','-u','-t',window,'@cockpit-store-revision')
    else:
        clone = tmux(sock,'new-window','-d','-P','-F','#{window_id}','-t','a','sleep 300')
        for key,value in (('window-role','skaldos.dix-cockpit.store-window.v1'),
                          ('store-id',args['store_id']),('store-revision',args['revision']),('store-session','a')):
            tmux(sock,'set-option','-w','-t',clone,'@cockpit-'+key,value)
    before = tmux(sock,'list-panes','-a','-F','#{pane_id} #{pane_pid} #{pane_dead}')
    with pytest.raises(RuntimeError,match='foreign|duplicate|inconsistent'):
        bound.api.require('open_store')(**args)
    assert tmux(sock,'list-panes','-a','-F','#{pane_id} #{pane_pid} #{pane_dead}') == before


def test_store_open_is_serialized_and_rollbacks_are_ownership_bounded(store_graph, monkeypatch):
    bound, args, _ = workspace(store_graph)
    with ThreadPoolExecutor(max_workers=3) as pool:
        values = list(pool.map(lambda _: bound.api.require('open_store')(**args), range(3)))
    assert len({v['window_id'] for v in values}) == 1
    window = values[0]['window_id']; sock=args['socket']
    browser = values[0]['panes']['browser']['pane_id']
    old_pid = tmux(sock,'display-message','-p','-t',browser,'#{pane_pid}')
    original=bound.runtime._run
    def refuse(command):
        if 'respawn-pane' in command and command[-1]=='refused-view':
            return subprocess.CompletedProcess(command,1,'','test-only spawn refusal')
        return original(command)
    monkeypatch.setattr(bound.runtime,'_run',refuse)
    other = {**args,'store_id':'fresh-failure','commands':{'status':['refused-view'],'browser':['sleep','300']}}
    with pytest.raises(RuntimeError,match='spawn refusal'):
        bound.api.require('open_store')(**other)
    assert len(tmux(sock,'list-windows','-t','a').splitlines())==2
    changed = {**args,'revision':'c'*32, 'commands':{'status':['refused-view'],'browser':['sleep','300']}}
    with pytest.raises(RuntimeError,match='spawn refusal'):
        bound.api.require('open_store')(**changed)
    assert old_pid != tmux(sock,'display-message','-p','-t',browser,'#{pane_pid}')
    assert tmux(sock,'show-option','-w','-v','-t',window,'@cockpit-store-revision') == args['revision']


def test_session_open_store_passes_only_identity_to_views(store_graph, monkeypatch):
    create, _, _ = store_graph
    bound = create('skaldos/cockpit/cockpit_session')
    started = bound.api.require('start')(
        session='a', shell_command=['sleep','300'], status_command=['sleep','300'], attach=False)
    calls = []
    class Api:
        def require(self, name):
            assert name=='open_store'
            return lambda **values:calls.append(values) or values
    bound.runtime.tmux=Api()
    monkeypatch.setattr(bound.runtime,'status',lambda **values:{'running':True})
    monkeypatch.setattr(bound.runtime,'paths',lambda **values:{'socket':started['tmux']['socket']})
    monkeypatch.setenv('DIX_BIN','/tmp/bin')
    result=bound.api.require('open_store')(store_id='saved',revision='a'*32,session='a',logo='roba')
    assert result['socket']==started['tmux']['socket']
    assert result['commands']=={
        'status':['/tmp/bin/dix-cockpit-store-status','--session','a','--store-id','saved','--logo','roba'],
        'browser':['/tmp/bin/dix-cockpit-store-browser','--session','a','--store-id','saved','--logo','roba']}
