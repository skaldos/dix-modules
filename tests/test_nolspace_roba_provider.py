from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path
from roba import RobaClient, create_context, start_daemon, stop_daemon
from roba.transport import TransportClient

ROOT=Path(__file__).parents[1]


@pytest.fixture
def native_nolspace():
    root=Path(tempfile.mkdtemp(prefix='n69-',dir='/tmp'))
    env={'ROBA_RUNTIME_ROOT':str(root/'r'),'ROBA_LOGS_ROOT':str(root/'l')}
    daemon=start_daemon('test',env=env)
    r=create_core_component_registry();mods=r.require('module',ModuleComponent);comps=r.require('composition',CompositionComponent)
    loaded=[];ids=[]
    for name in ('dix/state','dix/cli','dix/norn','dix/roba'):
        mods.load_module(first_party_module_path(name),module_id=name);loaded.append(name)
    for name in ('core','roba'):
        ident='skaldos/stores/nolspace/'+name
        mods.load_module(ROOT/'stores/nolspace'/name,module_id=ident);loaded.append(ident)
    def create(use):
        ident=str(len(ids));item=comps.create_instance(CompositionInstanceSpec(ident,use,{},ROOT),owner_scope_id='native')
        ids.append(ident);return item
    try:
        ctx=create_context(context_id='alpha',control=str(daemon.control_locator),control_token=daemon.control_token,env=env)
        owner=RobaClient(env={}).context(locator=str(ctx.direct_locator),token=ctx.owner_token)
        state={'same':'context value','text':'long-'+'x'*200,'integer':7,'number':1.5,'boolean':True,
               'null':None,'array':[1,{'nested':'x'}],'object':{'nested':[1,None]}}
        for key,value in state.items():owner.set(key,value)
        owner.instance_create(instance_id='same',state={**state,'same':'instance value'})
        base={'context_id':'alpha','context_locator':str(ctx.direct_locator),'token':ctx.owner_token,'timeout':2.0}
        yield create,owner,base,root
    finally:
        stop_daemon(daemon='id:test',env=env)
        for ident in reversed(ids):comps.destroy_instance('native',ident)
        for name in reversed(loaded):mods.unload_module(name)
        shutil.rmtree(root)


def test_real_roba_nolspace_lazy_collision_and_authoritative_rights(native_nolspace,monkeypatch):
    create,owner,base,_=native_nolspace
    boot=create('skaldos/stores/nolspace/roba/connection').api
    provider=create('skaldos/stores/nolspace/roba/provider').api
    api=create('skaldos/stores/nolspace/core/api').api
    assert {f.id for f in provider.functions()}=={'enumerate','lookup','upsert','delete'}
    before=json.dumps(owner.snapshot(),sort_keys=True)
    calls=[]; original=TransportClient.request
    def spy(self,method,path,**kwargs):
        assert 'snapshot' not in path, 'Enumeration/lookup must never use a snapshot'
        result=original(self,method,path,**kwargs)
        calls.append((method,path,result))
        return result
    monkeypatch.setattr(TransportClient,'request',spy)
    root=boot.require('root')(base)
    assert api.require('enumerate')(provider,root)==[{'name':'values'},{'name':'instances'}]
    values=api.require('lookup')(provider,root,'values');instances=api.require('lookup')(provider,root,'instances')
    refs=api.require('enumerate')(provider,values)
    assert all(set(item)=={'name'} for item in refs)
    assert api.require('enumerate')(provider,instances)==[{'name':'same'}]
    assert not any('/state/' in path for _,path,_ in calls)
    assert all(set(result)=={'keys'} for _,path,result in calls if path.endswith('state-keys'))
    item=api.require('lookup')(provider,values,'same');assert item['value']=='context value'
    child=api.require('lookup')(provider,instances,'same')
    assert api.require('lookup')(provider,child,'same')['value']=='instance value'
    for key,kind in [('integer','integer'),('number','number'),('boolean','boolean'),('null','null'),('array','array'),('object','object')]:
        assert api.require('lookup')(provider,values,key)['type']==kind
    with pytest.raises(ValueError):api.require('upsert')(provider,values,{'name':'array','type':'array','value':[]})
    assert len([1 for method,path,_ in calls if method=='GET' and path.endswith('/state/same')])==2
    monkeypatch.setattr(TransportClient,'request',original)
    assert json.dumps(owner.snapshot(),sort_keys=True)==before
    # Authentic delegated principal, not a UI-only cap check.
    reader=owner.token_create(token_id='reader',read=['context','instance:same'])['token']
    ro=boot.require('root')({**base,'token':reader,'instance_id':'same'})
    assert ro['value']['caps']==['enumerate','lookup']
    forged=copy.deepcopy(ro);forged['value']['caps']+=['upsert','delete']
    for op,arg in [('upsert',{'name':'same','type':'string','value':'forbidden'}),('delete','same')]:
        with pytest.raises(RuntimeError,match='does not permit'):provider.require(op)(forged,arg)
    assert owner.with_scope('id:same').get('same')=='instance value'


def test_real_write_only_does_no_key_or_value_reads_and_rw_is_atomic(native_nolspace,monkeypatch):
    create,owner,base,_=native_nolspace
    boot=create('skaldos/stores/nolspace/roba/connection').api
    provider=create('skaldos/stores/nolspace/roba/provider').api
    api=create('skaldos/stores/nolspace/core/api').api
    writer=owner.token_create(token_id='writer',write=['instance:same'])['token']
    wo=boot.require('root')({**base,'token':writer,'instance_id':'same'})
    assert wo['value']['caps']==['upsert','delete']
    calls=[];original=TransportClient.request
    def spy(self,method,path,**kwargs):
        assert path.endswith('/connect') or method in ('PUT','DELETE')
        calls.append((method,path))
        return original(self,method,path,**kwargs)
    monkeypatch.setattr(TransportClient,'request',spy)
    for op in ('enumerate','lookup'):
        with pytest.raises(PermissionError):api.require(op)(provider,wo,*(['same'] if op=='lookup' else []))
    assert calls==[]
    item={'name':'new','type':'null','value':None}
    assert api.require('upsert')(provider,wo,item)==item
    assert api.require('delete')(provider,wo,'new')=={'name':'new'}
    assert [method for method,_ in calls if method!='GET']==['PUT','DELETE']
    assert [path for method,path in calls if method=='GET']==['/context/connect','/context/connect']
    monkeypatch.setattr(TransportClient,'request',original)
    rw_token=owner.token_create(token_id='rw',read=['instance:same'],write=['instance:same'])['token']
    rw=boot.require('root')({**base,'token':rw_token,'instance_id':'same'})
    for kind,value in [('string','unquoted'),('integer',19),('number',2.5),('boolean',False),('null',None)]:
        api.require('upsert')(provider,rw,{'name':'fresh','type':kind,'value':value})
        assert owner.with_scope('id:same').get('fresh')==value
    api.require('delete')(provider,rw,'fresh')
    # Without Context-read a known write-only Instance remains discoverable as a Child.
    root=boot.require('root')({**base,'token':writer})
    children=api.require('lookup')(provider,root,'instances')
    assert api.require('enumerate')(provider,children)==[{'name':'same'}]
    assert api.require('lookup')(provider,children,'same')['value']['caps']==['upsert','delete']
    invalid={**base,'token':'wrong-local-test-token'}
    with pytest.raises(RuntimeError) as exc:boot.require('root')(invalid)
    assert invalid['token'] not in str(exc.value)
    with pytest.raises(ValueError):boot.require('validate')({**base,'context_locator':'id:guess'})


def test_bad_access_cannot_use_owner_environment_and_bad_values_never_write(native_nolspace,monkeypatch):
    create,owner,base,_=native_nolspace
    boot=create('skaldos/stores/nolspace/roba/connection').api
    provider=create('skaldos/stores/nolspace/roba/provider').api
    monkeypatch.setenv('ROBA_CTX_TOKEN',base['token'])
    monkeypatch.setenv('ROBA_CONTEXT',base['context_locator'])
    monkeypatch.setenv('ROBA_CONTROL_TOKEN',base['token'])
    wrong={**base,'token':'invalid-explicit-token'}
    with pytest.raises(RuntimeError) as error:boot.require('root')(wrong)
    assert wrong['token'] not in str(error.value)
    with pytest.raises(RuntimeError,match='Context id differs'):
        boot.require('root')({**base,'context_id':'other'})
    root=boot.require('root')(base)
    view=provider.require('lookup')(root,'values')
    calls=[];original=TransportClient.request
    def spy(self,method,path,**kwargs):
        calls.append((method,path));return original(self,method,path,**kwargs)
    monkeypatch.setattr(TransportClient,'request',spy)
    for kind,value in [('integer',True),('number',float('inf')),('object',{'nested':1}),
                       ('array',[1]),('vendor',{'x':2}),('nolspace',{'caps':[]})]:
        with pytest.raises(ValueError):provider.require('upsert')(view,{'name':'text','type':kind,'value':value})
    assert calls==[]
    monkeypatch.setattr(TransportClient,'request',original)
    assert owner.get('text').startswith('long-')


def test_explicit_native_socket_capability_needs_no_token_or_environment(native_nolspace, monkeypatch):
    create, owner, base, _ = native_nolspace
    boot = create('skaldos/stores/nolspace/roba/connection').api
    provider = create('skaldos/stores/nolspace/roba/provider').api
    socket = owner.socket_create(socket_id='reader', read=['instance:same'])['socket']
    connection = {key: value for key, value in base.items() if key != 'token'}
    connection.update(context_locator='unix:' + socket, instance_id='same')
    monkeypatch.setenv('ROBA_CTX_TOKEN', base['token'])
    root = boot.require('root')(connection)
    assert root['value']['caps'] == ['enumerate', 'lookup']
    assert provider.require('lookup')(root, 'same')['value'] == 'instance value'
    with pytest.raises(RuntimeError, match='does not permit'):
        provider.require('delete')(root, 'same')
