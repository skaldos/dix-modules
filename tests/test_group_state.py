from pathlib import Path
import json
from dix.core.composition import CompositionRuntimeContext

def ctx(root): return CompositionRuntimeContext(instance_id='x',composition_id='skaldos/sway/groups',module_id='skaldos/sway',module_root=root,composition_root=root,config_base_dir=root,owner_scope_id='x')

def test_group_ownership_and_projection(tmp_path,load_runtime,api):
    calls=[]; focus=[34]; live=[34,32]
    members=[]; targets=[]
    State=api(set=lambda value:(calls.append(value) or True)); Ipc=api(focused_con_id=lambda:focus[0],live_con_ids=lambda:list(live))
    Active=api(set=lambda value:members.append(value)); Target=api(set=lambda value:targets.append(value))
    Runtime=load_runtime('sway/compositions/groups/runtime.py')
    r=Runtime(context=ctx(tmp_path),config={'state_file':str(tmp_path/'groups.json')},state=State,ipc=Ipc,active_members=Active,navigation_target=Target)
    r.create('work'); r.create('private'); assert calls[-1]=={'groups':['work','private'],'active_group':''}
    assert r.add('work') is True; assert r.add('work') is False
    assert r.add('private') is True; assert r.memberships()==['work','private']
    assert r.select('work') is True; assert members[-1]==[34] and targets[-1]=='group'
    calls_before=len(calls); assert r.select('work') is False; assert len(calls)==calls_before
    focus[0]=32; assert r.add('work') is True; live[:]=[32]; assert r.select('work') is False; assert members[-1]==[32]
    assert r.show('work')==[34,32]
    assert r.deactivate() is True; assert targets[-1]=='basic' and members[-1]==[]
    calls_before=len(calls); assert r.deactivate() is False and len(calls)==calls_before
    value=json.loads((tmp_path/'groups.json').read_text()); assert value['groups']['work']==[34,32]

def test_active_members_and_target_are_strict_atomic(tmp_path,load_runtime):
    Active=load_runtime('sway/compositions/active_members/runtime.py'); Target=load_runtime('sway/compositions/navigation_target/runtime.py')
    c=ctx(tmp_path); a=Active(context=c,config={'path':str(tmp_path/'members')}); t=Target(context=c,config={'path':str(tmp_path/'target')})
    assert a.get()==[] and t.get()=='basic'; a.set([34,32]); assert (tmp_path/'members').read_bytes()==b'34 32\n' and a.get()==[34,32]
    t.set('group'); assert t.get()=='group'
    (tmp_path/'members').write_text('034\n');
    import pytest
    with pytest.raises(ValueError): a.get()
    (tmp_path/'target').write_text('group')
    with pytest.raises(ValueError): t.get()
