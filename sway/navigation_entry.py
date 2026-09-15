from __future__ import annotations
import argparse, importlib.util, json, os, sys, time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

_DIRECTIONS=("left","right","up","down")
class Api:
    def __init__(self,values:dict[str,Callable[...,object]]):self.values=values
    def require(self,name:str)->Callable[...,object]:return self.values[name]

def execute(module_root:Path,direction:str,target:str|None=None)->dict[str,object]:
    if direction not in _DIRECTIONS: raise ValueError(f"unsupported direction: {direction!r}")
    route=_runtime(module_root/'compositions/navigation_target/runtime.py','skaldos_sway_route')
    route_object=route.Runtime(context=_composition_context(module_root,'navigation_target'),config={})
    selected=target if target is not None else route_object.get()
    if selected not in {'basic','group'}: raise ValueError(f"unsupported target: {selected!r}")
    ipc_mod=_runtime(module_root/'compositions/ipc/runtime.py','skaldos_sway_ipc')
    basic_mod=_runtime(module_root/'apps/navigation_basic/runtime.py','skaldos_sway_basic')
    ipc=ipc_mod.Runtime(context=_composition_context(module_root,'ipc'),config={})
    ipc_api=Api({name:getattr(ipc,name) for name in ('focused_con_id','focus_direction','focus_con_id','live_con_ids')})
    basic=basic_mod.Runtime(context=_application_context(module_root,'navigation_basic'),config={},ipc=ipc_api)
    if selected=='basic': runner=basic
    else:
        active_mod=_runtime(module_root/'compositions/active_members/runtime.py','skaldos_sway_active_members')
        group_mod=_runtime(module_root/'apps/navigation_group/runtime.py','skaldos_sway_group_navigation')
        active=active_mod.Runtime(context=_composition_context(module_root,'active_members'),config={})
        group=group_mod.Runtime(context=_application_context(module_root,'navigation_group'),config={},basic=Api({name:getattr(basic,name) for name in _DIRECTIONS}),active_members=Api({'get':active.get}),ipc=ipc_api)
        runner=group
    result=getattr(runner,direction)()
    if not isinstance(result,dict): raise TypeError("navigation result must be a dictionary")
    return result

def main(argv:list[str]|None=None,module_root:Path|None=None)->int:
    parser=argparse.ArgumentParser(prog='skaldos-sway-nav')
    parser.add_argument('direction',choices=_DIRECTIONS)
    parser.add_argument('--target',choices=('basic','group'))
    args=parser.parse_args(argv)
    try:
        result=execute(module_root or Path(__file__).resolve().parent,args.direction,args.target)
    except Exception as exc:
        print(f"runtime error: {exc}",file=sys.stderr); return 1
    print(json.dumps(result,sort_keys=True,separators=(',',':'))); return 0

def _runtime(path:Path,name:str)->ModuleType:
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"cannot load runtime: {path}")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def _composition_context(root:Path,owner:str):
    from dix.core.composition import CompositionRuntimeContext
    return CompositionRuntimeContext(instance_id='navigation-entry',composition_id=f'skaldos/sway/{owner}',module_id='skaldos/sway',module_root=root,composition_root=root,config_base_dir=root,owner_scope_id='navigation-entry')
def _application_context(root:Path,owner:str):
    from dix.core.application import ApplicationRuntimeContext
    return ApplicationRuntimeContext(instance_id='navigation-entry',application_id=f'skaldos/sway/{owner}',module_id='skaldos/sway',module_root=root,application_root=root,config_base_dir=root,owner_scope_id='navigation-entry')
if __name__=='__main__':raise SystemExit(main())
