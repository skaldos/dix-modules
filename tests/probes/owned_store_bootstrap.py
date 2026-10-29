"""Test/manual bootstrap through existing DIX ROBA Loom; never an installed runner."""
from __future__ import annotations


def populate(create, session='dix', catalog_session=None):
    catalog_session = session if catalog_session is None else catalog_session
    runtime = create('skaldos/cockpit/roba_runtime').api
    env = runtime.require('owner_environment')(session=session)
    paths = runtime.require('paths')(session=session)
    seed = {'daemon_id':'default','runtime_root':env['ROBA_RUNTIME_ROOT'],
            'logs_root':env['ROBA_LOGS_ROOT'],'timeout':5.0,
            'pid':runtime.require('status')(session=session)['pid'],
            'daemon_socket':paths['daemon_socket'],'control_socket':paths['control_socket'],
            'control_token':env['ROBA_CONTROL_TOKEN']}
    execute = create('dix/roba/loom').api.require('execute')

    def ref(items, ident):
        found=[item for item in items if item['object_id']==ident]
        if len(found)!=1:
            raise RuntimeError('Bootstrap expected exactly one '+ident+' reference')
        return found[0]['value']

    def store_offers(connection):
        target=ref(execute(connection,'connection'),'store')
        connect=ref(execute(target,'store'),'connect')
        return execute(connect,'connect')

    def write_values(connection, state):
        target=ref(execute(connection,'connection'),'data')
        connect=ref(execute(target,'data'),'connect')
        write=ref(execute(connect,'connect'),'write')
        for key,value in state.items():
            execute({**write,'key':key,'value':value},'write')

    control=ref(execute(seed),'connection')
    create_context=ref(store_offers(control),'create')
    catalog=create('skaldos/cockpit/store_browser').runtime.catalog
    connections={}
    for label,active,priority in (('alpha',True,7),('beta',False,21)):
        context=ref(execute({**create_context,'context_id':'up068-'+label,'name':label.title()},'create'),'connection')
        state={'project':label+' context','cwd':'/work/'+label,'active':active,'priority':priority,
               'refs':[{'name':'docs','file':label+'/README.md'},{'name':'code','file':label+'/src'}],
               'settings':{'colors':{'primary':label},'enabled':active}}
        write_values(context,state)
        request=ref(store_offers(context),'create')
        instance=ref(execute({**request,'instance_id':label+'-work','name':label.title()+' Work',
                             'state':{**state,'project':label+' instance'}},'create'),'connection')
        for ident,connection in ((label+'-context',context),(label+'-work',instance)):
            # The connection is the Store, not a second registry or connection object.
            catalog.require('create')({'store_id':ident,'provider':'roba','connection':connection},catalog_session)
            connections[ident]=catalog.require('get')(ident,catalog_session)['connection']
    return connections
