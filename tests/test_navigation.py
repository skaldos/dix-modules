import json,sys
from pathlib import Path
from dix.core.application import ApplicationRuntimeContext

def test_navigation_basic_and_group(load_runtime,api,tmp_path):
    current=[10]; sequence=iter([20,30]); commands=[]
    def direction(value): commands.append(value); current[0]=next(sequence)
    ipc=api(focused_con_id=lambda:current[0],focus_direction=direction,focus_con_id=lambda value:current.__setitem__(0,value),live_con_ids=lambda:[10,20,30])
    Basic=load_runtime('sway/apps/navigation_basic/runtime.py'); Group=load_runtime('sway/apps/navigation_group/runtime.py')
    c=ApplicationRuntimeContext(instance_id='x',application_id='x',module_id='x',module_root=tmp_path,application_root=tmp_path,config_base_dir=tmp_path,owner_scope_id='x')
    basic=Basic(context=c,config={},ipc=ipc); assert basic.right()['focused_id']==20
    current[0]=10; sequence=iter([20,30]); group=Group(context=c,config={},basic=api(**{x:getattr(basic,x) for x in ('left','right','up','down')}),active_members=api(get=lambda:[30,99]),ipc=ipc)
    result=group.right(); assert result['matched'] is True and result['focused_id']==30 and result['stale_ids']==[99]

def test_navigation_entry_is_route_first_lazy(tmp_path,monkeypatch):
    import importlib.util
    root=Path(__file__).parents[1]/'sway'; route=tmp_path/'route'; members=tmp_path/'members'
    route.write_text('basic\n'); members.write_text('99\n')
    monkeypatch.setenv('SKALDOS_SWAY_NAVIGATION_TARGET_FILE',str(route)); monkeypatch.setenv('SKALDOS_SWAY_ACTIVE_MEMBERS_FILE',str(members))
    class Node:
        id=34
    class Tree:
        def find_focused(self): return Node()
        def leaves(self): return [Node()]
    class Reply: success=True; error=None
    class Conn:
        def get_tree(self): return Tree()
        def command(self,value): return [Reply()]
    import i3ipc; monkeypatch.setattr(i3ipc,'Connection',Conn)
    spec=importlib.util.spec_from_file_location('nav_entry',root/'navigation_entry.py'); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    before=set(sys.modules); assert mod.main(['left'],root)==0
    loaded=set(sys.modules)-before
    assert not any('group_navigation' in name or 'active_members' in name for name in loaded)
    route.write_text('invalid\n')
    assert mod.main(['left'],root)==1
