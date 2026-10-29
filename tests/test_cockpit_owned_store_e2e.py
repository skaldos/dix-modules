from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from probes.owned_store_bootstrap import populate
from roba import RobaClient
from test_cockpit_interaction_install import (
    installed_ui as installed_ui,  # noqa: PLC0414 - pytest fixture re-export
)
from test_cockpit_store_workspace import tmux, wait_for


@pytest.fixture
def real_owned_ui(request, store_graph):
    # Start the native target daemon before attaching a PTY drain thread.
    _create, runtime, _ = store_graph
    runtime.require('start')(session='b')
    return request.getfixturevalue('installed_ui')


def test_installed_owned_stores_with_two_real_contexts_and_instances(real_owned_ui):
    create, _workspace, _, started, _, _, root = real_owned_ui
    runtime = create('skaldos/cockpit/roba_runtime').api
    env = runtime.require('owner_environment')(session='b')
    control = RobaClient(env=env).control()
    browser_api = create('skaldos/cockpit/store_browser').api
    catalog = create('skaldos/cockpit/store_browser').runtime.catalog
    owners, secrets, snapshots = {}, [env['ROBA_CONTROL_TOKEN']], {}
    secrets.append(runtime.require('owner_environment')(session='a')['ROBA_CONTROL_TOKEN'])
    connections=populate(create,session='b',catalog_session='a')
    for label in ('alpha','beta'):
        conn=connections[label+'-context']
        secrets.append(conn['token'])
        owner=RobaClient(env={}).context(locator=conn['context_locator'],token=conn['token'])
        owners[label]=owner
        snapshots[label]=owner.snapshot()
    store_count=len(catalog.require('list')('a')); assert store_count==4
    before = json.dumps(snapshots,sort_keys=True)
    assert not any(secret in before for secret in secrets)
    contexts_before=control.contexts()
    sock, store = started['tmux']['socket'],started['store']['pane_id']
    evidence={'windows':{},'events':[],'target_before':snapshots}

    def safe(value):
        text = str(value)
        for secret in secrets:
            text=text.replace(secret,'[private capability]')
        for connection in connections.values():
            text=text.replace(connection['context_locator'],'unix:[private locator]')
        return text

    def screen(pane, history=False):
        flags=('-S','-') if history else ()
        return tmux(sock,'capture-pane','-p',*flags,'-t',pane)

    def keys(pane,*values):
        tmux(sock,'send-keys','-t',pane,*values); time.sleep(.16)

    def command(token):
        keys(store,':'); keys(store,token,'Enter')

    def windows(sid):
        raw=tmux(sock,'list-windows','-t','a','-F','#{window_id}\t#{@cockpit-store-id}')
        return [line.split('\t')[0] for line in raw.splitlines() if line.split('\t')[1:]==[sid]]

    def panes(window):
        raw=tmux(sock,'list-panes','-t',window,'-F','#{pane_id}\t#{@cockpit-pane-role}\t#{pane_pid}\t#{pane_dead}')
        result={}
        for line in raw.splitlines():
            ident,role,pid,dead=line.split('\t')
            key='status' if role=='skaldos.dix-cockpit.store-status.v1' else 'browser'
            result[key]={'id':ident,'pid':pid,'dead':dead,'role':role}
        assert len(result)==2
        return result

    def select(sid):
        tmux(sock,'select-window','-t','a:control'); tmux(sock,'select-pane','-t',store)
        keys(store,'C-r'); keys(store,'g','g')
        entries=catalog.require('list')('a')
        index=[entry['store_id'] for entry in entries].index(sid)
        for _ in range(index): keys(store,'Down')

    def opened(sid):
        select(sid); command('o')
        try:
            wait_for(lambda: len(windows(sid))==1)
            win=windows(sid)[0]
            wait_for(lambda: tmux(sock,'display-message','-p','#{window_id}')==win)
            pair=panes(win)
            wait_for(lambda: 'READ ONLY' in screen(pair['browser']['id']) and 'settings' in screen(pair['browser']['id']))
            wait_for(lambda: catalog.require('record')(sid,'a')['revision'] in screen(pair['status']['id'],True))
        except AssertionError:
            detail=safe(screen(store))
            for existing in windows(sid):
                for role, view in panes(existing).items():
                    detail+='\n'+role+': '+safe(screen(view['id'],True))
            raise AssertionError('Store workspace did not become ready: '+detail) from None
        return win,pair

    def transport_boundary(win,pair):
        meta=tmux(sock,'show-options','-w','-t',win)+tmux(sock,'show-environment','-t','a')
        for pane in pair.values():
            meta+=tmux(sock,'show-options','-p','-t',pane['id'])
            meta+=tmux(sock,'display-message','-p','-t',pane['id'],'#{pane_title} #{pane_start_command}')
            pending=[int(pane['pid'])]
            while pending:
                pid=pending.pop()
                try:
                    data=Path(f'/proc/{pid}/cmdline').read_bytes()+Path(f'/proc/{pid}/environ').read_bytes()
                    assert not any(secret.encode() in data for secret in secrets)
                    pending += [int(p) for p in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
                except FileNotFoundError:
                    pass  # An optional short-lived logo renderer can finish during the read.
        assert not any(secret in meta for secret in secrets)
        return meta

    for sid in sorted(connections):
        win,pair=opened(sid)
        status=screen(pair['status']['id'],True)
        shown=connections[sid]['token'] in status  # Owner display is intentional; failure output must not echo it.
        assert shown, 'Status did not expose the intended private owner view'
        assert sid in status and catalog.require('record')(sid,'a')['revision'] in status
        if 'instance_id' in connections[sid]: assert connections[sid]['instance_id'] in status
        pane=pair['browser']['id']
        model=browser_api.require('create_selected_session')(sid,'a')
        labels=[node['label'] for node in model.reload()]
        if sid.endswith('context'): assert sid.removesuffix('context')+'work' in labels
        else: assert sid not in labels
        # Drive the installed browser through list -> object -> root and object -> root.
        for field in ('refs','settings'):
            keys(pane,'g','g')
            for _ in range(labels.index(field)): keys(pane,'Down')
            keys(pane,'Enter')
            wait_for(lambda field=field, pane=pane: field in screen(pane))
            if field=='refs':
                keys(pane,'Enter');wait_for(lambda pane=pane: 'file' in screen(pane))
            keys(pane,'z','U')
            wait_for(lambda pane=pane: 'settings' in screen(pane) and 'priority' in screen(pane))
        for field in ('project','active','priority'):
            keys(pane,'g','g')
            for _ in range(labels.index(field)): keys(pane,'Down')
            keys(pane,'Enter');keys(pane,'Enter')
            expected=(sid.split('-')[0]+(' instance' if 'instance_id' in connections[sid] else ' context')
                      if field=='project' else ('true' if sid.startswith('alpha') else 'false')
                      if field=='active' else ('7' if sid.startswith('alpha') else '21'))
            wait_for(lambda pane=pane, expected=expected: 'Read-only Store value' in screen(pane) and expected in screen(pane))
            keys(pane,'q');keys(pane,'z','U')
            wait_for(lambda pane=pane: 'settings' in screen(pane) and 'priority' in screen(pane))
        for key in ('N','E','R','X'): keys(pane,'z',key)
        same,same_pair=opened(sid)
        assert same==win and {k:p['pid'] for k,p in same_pair.items()}=={k:p['pid'] for k,p in pair.items()}
        meta=transport_boundary(win,same_pair)
        evidence['windows'][sid]={'window_id':win,'panes':same_pair,'metadata':meta,
                                  'status':safe(status),'browser':safe(screen(pane))}
    sid='alpha-context';win,pair=opened(sid)
    tmux(sock,'rename-window','-t',win,'owner-chosen-name')
    tmux(sock,'move-window','-s',win,'-t','a:9')
    assert opened(sid)[0]==win
    # Ended browser repaired in place; missing status recreated without replacing healthy browser.
    browser, status = pair['browser']['id'],pair['status']['id']
    status_pid=pair['status']['pid']
    tmux(sock,'respawn-pane','-k','-t',browser,'exit 7')
    wait_for(lambda: tmux(sock,'display-message','-p','-t',browser,'#{pane_dead}')=='1')
    _,pair=opened(sid)
    assert pair['browser']['id']==browser and pair['status']['pid']==status_pid
    browser_pid=pair['browser']['pid']
    tmux(sock,'kill-pane','-t',status)
    _,pair=opened(sid)
    assert pair['status']['id']!=status and pair['browser']['pid']==browser_pid
    # Save a changed timeout in the actual installed master Store editor, then :o rebuilds both views.
    old_pids={k:p['pid'] for k,p in pair.items()}
    old_revision=catalog.require('record')(sid,'a')['revision']
    select(sid);keys(store,'Enter');keys(store,'Down','Down','Enter')
    wait_for(lambda:'context_locator' in screen(store))
    keys(store,'g','g')
    for _ in range(list(catalog.require('get')(sid,'a')['connection']).index('timeout')): keys(store,'Down')
    keys(store,'Enter');tmux(sock,'send-keys','-t',store,'-l','1.25');keys(store,'Enter');keys(store,'q')
    command('w');keys(store,'q')
    assert catalog.require('record')(sid,'a')['revision']!=old_revision
    rebuilt,pair=opened(sid)
    assert rebuilt==win and all(pair[k]['pid']!=old_pids[k] for k in pair)
    transport_boundary(win,pair)
    # Corrupt ownership is rejected from :o without touching either foreign pane.
    browser=pair['browser']['id']
    tmux(sock,'set-option','-p','-t',browser,'@cockpit-pane-role','foreign.owner')
    saved=tmux(sock,'list-panes','-t',win,'-F','#{pane_id} #{pane_pid}')
    select(sid);command('o')
    wait_for(lambda:'foreign' in screen(store))
    assert tmux(sock,'list-panes','-t',win,'-F','#{pane_id} #{pane_pid}')==saved
    tmux(sock,'set-option','-p','-t',browser,'@cockpit-pane-role','skaldos.dix-cockpit.selected-browser.v1')
    tmux(sock,'kill-window','-t',win)
    fresh,pair=opened(sid);assert fresh!=win
    # Provider failure is local and visible, not a window/catalog deletion or target repair.
    definition=catalog.require('get')(sid,'a');bad={**definition,'connection':{
        **definition['connection'],'context_locator':'unix:'+str(root/'absent.sock')}}
    catalog.require('update')(sid,bad,'a')
    select(sid);command('o')
    wait_for(lambda: panes(fresh)['browser']['pid']!=pair['browser']['pid'])
    failed=panes(fresh)
    wait_for(lambda:'Error' in screen(failed['browser']['id']))
    unchanged=catalog.require('get')(sid,'a')==bad
    assert failed['browser']['dead']=='0' and unchanged
    assert not any(secret in screen(failed['browser']['id']) for secret in secrets)
    catalog.require('update')(sid,definition,'a');opened(sid)
    after=json.dumps({label:owner.snapshot() for label,owner in owners.items()},sort_keys=True)
    assert after==before and control.contexts()==contexts_before
    store_count=len(catalog.require('list')('a')); assert store_count==4
    evidence.update(target_after=json.loads(after),target_unchanged=True,
                    owner_status_visible=True,secret_transport=False,
                    events=['create-four','focus','navigate-read-only','rename','move','repair-dead',
                            'repair-missing','ui-save-revision-rebuild','foreign-rejected','recreate','provider-error'])
    destination=os.environ.get('DIX_OWNED_STORE_EVIDENCE_DIR')
    if destination:
        out=Path(destination);out.mkdir(parents=True,exist_ok=True)
        payload=json.dumps(evidence,ensure_ascii=False,indent=2)
        assert not any(secret in payload for secret in secrets)
        (out/'owned-store-proof.json').write_text(payload)
        (out/'target-before.json').write_text(before+'\n')
        (out/'target-after.json').write_text(after+'\n')
