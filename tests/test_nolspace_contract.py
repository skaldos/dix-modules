from __future__ import annotations

from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


@pytest.fixture
def nolspace_graph():
    registry = create_core_component_registry()
    modules = registry.require('module', ModuleComponent)
    comps = registry.require('composition', CompositionComponent)
    modules.load_module(first_party_module_path('dix/norn'), module_id='dix/norn')
    modules.load_module(ROOT/'stores/nolspace/core', module_id='skaldos/stores/nolspace/core')
    instances = []
    def create(use):
        ident = str(len(instances))
        instance = comps.create_instance(CompositionInstanceSpec(ident, use, {}, ROOT), owner_scope_id='nolspace')
        instances.append(ident)
        return instance
    yield create
    for ident in reversed(instances): comps.destroy_instance('nolspace', ident)
    modules.unload_module('skaldos/stores/nolspace/core'); modules.unload_module('dix/norn')


def test_core_shapes_and_standard_types_are_strict_and_detached(nolspace_graph):
    contract = nolspace_graph('skaldos/stores/nolspace/core/contract').api
    for kind, value in (('string','s'),('integer',3),('number',1.2),('boolean',True),('null',None),
                        ('array',[1,False,None]),('object',{'a':[]}),('vendor.type',{'x':3}),
                        ('nolspace',{'caps':[], 'target':{'own':'opaque'}})):
        item={'name':'kept name','type':kind,'value':value}
        out=contract.require('object')(item)
        assert out==item
        if isinstance(value, dict):
            out['value']['extra']=1; assert 'extra' not in value
    for kind,value in (('integer',True),('boolean',1),('null',0),('number',float('nan')),
                       ('number',float('inf')),('number',False),('array',{}),('object',[]),
                       ('string',2),('vendor',object())):
        with pytest.raises(ValueError): contract.require('object')({'name':'x','type':kind,'value':value})
    for bad in ({}, {'name':''}, {'name':'  '}, {'name':3}, {'name':'x','value':3}):
        with pytest.raises(ValueError): contract.require('reference')(bad)
    for bad in ({'caps':['enter']},{'caps':['lookup','lookup']},{'caps':['upsert'],'target':[]},
                {'caps':'lookup'},{'caps':[],'provider':'magic'}):
        with pytest.raises(ValueError): contract.require('view')({'name':'x','type':'nolspace','value':bad})
    with pytest.raises(ValueError): contract.require('object')({'name':'x','value':1})


def test_core_exact_positive_surface_lazy_child_read_only_and_write_only(nolspace_graph):
    api=nolspace_graph('skaldos/stores/nolspace/core/api').api
    assert {f.id for f in api.functions()}=={'enumerate','lookup','upsert','delete'}
    calls=[]
    child={'name':'child','type':'nolspace','value':{'caps':['enumerate','lookup'],'target':{'child':True}}}
    class Provider:
        def require(self,name):
            assert name in {'enumerate','lookup','upsert','delete'}
            def call(view,*args):
                calls.append((name,view,args))
                if name=='enumerate': return [{'name':'item'}]
                if name=='lookup': return child if args[0]=='child' else {'name':args[0],'type':'integer','value':7}
                if name=='upsert': return args[0]
                return {'name':args[0]}
            return call
    provider=Provider()
    ro={'name':'r','type':'nolspace','value':{'caps':['enumerate','lookup']}}
    assert api.require('enumerate')(provider,ro)==[{'name':'item'}]
    assert [c[0] for c in calls]==['enumerate']
    for op in ('upsert','delete'):
        with pytest.raises(PermissionError):
            api.require(op)(provider,ro,{'name':'x','type':'integer','value':1} if op=='upsert' else 'x')
    assert len(calls)==1
    out=api.require('lookup')(provider,ro,'child')
    api.require('enumerate')(provider,out)
    assert calls[-1][1]==child and 'provider' not in out
    wo={'name':'w','type':'nolspace','value':{'caps':['upsert','delete']}}
    for op in ('enumerate','lookup'):
        with pytest.raises(PermissionError):
            api.require(op)(provider,wo,*(['x'] if op=='lookup' else []))
    api.require('upsert')(provider,wo,{'name':'new','type':'null','value':None})
    api.require('delete')(provider,wo,'new')
    assert [c[0] for c in calls][-2:]==['upsert','delete']
    assert api.require('lookup')(provider,ro,'item')['value']==7


def test_core_contains_no_backend_or_ui_imports():
    for path in (ROOT/'stores/nolspace/core').rglob('*.py'):
        for line in path.read_text().splitlines():
            if line.startswith(('import ','from ')):
                assert not any(word in line for word in ('roba','cockpit','visidata','tmux'))


@pytest.mark.parametrize('caps', [[], ['lookup'], ['upsert'], ['delete'], ['enumerate'],
                                ['enumerate','lookup','upsert','delete']])
def test_any_standard_capability_subset_and_opaque_optional_target(nolspace_graph,caps):
    contract=nolspace_graph('skaldos/stores/nolspace/core/contract').api
    for extra in ({}, {'target':{'arbitrary':{'nested':[3,None]}}}):
        value={'name':'view','type':'nolspace','value':{'caps':caps,**extra}}
        assert contract.require('view')(value)==value


def test_duplicate_or_mismatched_names_fail_without_resolution(nolspace_graph):
    api=nolspace_graph('skaldos/stores/nolspace/core/api').api
    view={'name':'v','type':'nolspace','value':{'caps':['enumerate','lookup','upsert','delete']}}
    class Bad:
        def require(self,op):
            if op=='enumerate':return lambda *_:[{'name':'x'},{'name':'x'}]
            if op=='delete':return lambda *_:{'name':'different'}
            return lambda *_:{'name':'different','type':'string','value':'x'}
    for op,arg in [('enumerate',[]),('lookup',['x']),('upsert',[{'name':'x','type':'null','value':None}]),('delete',['x'])]:
        with pytest.raises(ValueError): api.require(op)(Bad(),view,*arg)
