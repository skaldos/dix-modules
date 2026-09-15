from __future__ import annotations
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol
from dix.core.application import ApplicationApi, ApplicationRuntimeContext
class Api(Protocol):
    def require(self,function_id:str)->Callable[...,object]: ...
class Runtime:
    def __init__(self,*,context:ApplicationRuntimeContext,config:Mapping[str,object],typer:Api,groups:ApplicationApi)->None:
        self.context,self.config,self.typer,self.groups=context,config,typer,groups
    def main(self,argv:Sequence[str])->int:
        value=self.typer.require('invoke')(name='skaldos-sway',targets={'group':self.groups},argv=argv)
        if type(value) is not int: raise TypeError('Typer invoke must return an integer exit code')
        return value
