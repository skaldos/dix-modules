from __future__ import annotations
from collections.abc import Callable, Mapping
from typing import Protocol
from dix.core.application import ApplicationApi, ApplicationRuntimeContext
class Api(Protocol):
    def require(self,function_id:str)->Callable[...,object]: ...
class Runtime:
    def __init__(self,*,context:ApplicationRuntimeContext,config:Mapping[str,object],basic:ApplicationApi,active_members:Api,ipc:Api)->None:
        self.context,self.config,self.basic,self.active_members,self.ipc=context,config,basic,active_members,ipc
    def left(self)->dict[str,object]:return self._move("left")
    def right(self)->dict[str,object]:return self._move("right")
    def up(self)->dict[str,object]:return self._move("up")
    def down(self)->dict[str,object]:return self._move("down")
    def _move(self,direction:str)->dict[str,object]:
        members=_ids(self.active_members.require("get")(),"active members")
        if not members: return _mapping(self.basic.require(direction)(),"basic navigation")
        origin=_id(self.ipc.require("focused_con_id")(),"focused con_id")
        live_ids=_ids(self.ipc.require("live_con_ids")(),"live con_ids"); live=set(live_ids)
        stale=[value for value in members if value not in live]; allowed=set(members)&live
        visited=[origin]; seen={origin}; current=origin
        if not any(value!=origin for value in allowed): return _result(direction,origin,origin,False,True,visited,stale)
        for _ in range(max(1,len(live_ids)+1)):
            step=_mapping(self.basic.require(direction)(),"basic navigation")
            if step.get("direction")!=direction or step.get("origin_id")!=current: raise ValueError("basic navigation returned an inconsistent step")
            focused=_id(step.get("focused_id"),"step focused con_id")
            changed=step.get("changed")
            if type(changed) is not bool or changed!=(focused!=current): raise ValueError("basic navigation returned invalid changed")
            repeated=focused in seen
            if not repeated: seen.add(focused); visited.append(focused)
            current=focused
            if focused!=origin and focused in allowed: return _result(direction,origin,focused,True,False,visited,stale)
            if not changed or repeated: break
        if current!=origin:
            value=self.ipc.require("focus_con_id")(origin)
            if value is not None: raise TypeError("focus_con_id must return None")
            current=_id(self.ipc.require("focused_con_id")(),"restored con_id")
            if current!=origin: raise RuntimeError(f"Sway focus restore failed: expected {origin}, got {current}")
        return _result(direction,origin,current,False,True,visited,stale)
def _id(value:object,label:str)->int:
    if type(value) is not int or value<=0: raise TypeError(f"{label} must be a positive integer")
    return value
def _ids(value:object,label:str)->list[int]:
    if not isinstance(value,list): raise TypeError(f"{label} must be a list")
    result=[_id(v,label) for v in value]
    if len(set(result))!=len(result): raise ValueError(f"{label} must not contain duplicates")
    return result
def _mapping(value:object,label:str)->Mapping[str,object]:
    if not isinstance(value,Mapping): raise TypeError(f"{label} must return a mapping")
    return value
def _result(direction,origin,focused,matched,restored,visited,stale):
    return {"direction":direction,"origin_id":origin,"focused_id":focused,"matched":matched,"restored":restored,"visited_ids":list(visited),"stale_ids":list(stale)}
