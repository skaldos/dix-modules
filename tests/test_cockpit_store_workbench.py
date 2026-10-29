from __future__ import annotations

import copy
import importlib

import pytest


@pytest.fixture(autouse=True)
def preserve_process_keymap():
    from visidata import vd

    bindings = copy.deepcopy(dict(vd.bindkeys))
    menu = vd.options.disp_menu
    yield
    vd.bindkeys.clear()
    vd.bindkeys.update(bindings)
    vd.options.disp_menu = menu


def workbench(create):
    obj = create("skaldos/cockpit/store_workbench")
    ui = importlib.import_module(obj.runtime.__class__.__module__ + ".ui")
    return obj, ui


def test_staged_atomic_edits_save_failures_and_all_guards(store_graph):
    create, _, _ = store_graph
    obj, ui = workbench(create)
    session = obj.api.require("create_session")("a")
    assert session.reload_catalog() == []
    assert session.new("roba", lambda: "cancel")
    baseline = copy.deepcopy(session.baseline)
    session.edit(("store_id",), "test")
    session.edit(("connection", "context_id"), "missing")
    session.edit(("connection", "context_locator"), "unix:/tmp/missing.sock")
    session.edit(("connection", "token"), "private-staged-token")
    session.edit(("connection", "timeout"), "0.75")
    assert session.dirty and session.reload_catalog() == []
    before = session.draft.at()
    with pytest.raises(ValueError):
        session.edit(("connection", "timeout"), "bad-private-staged-token")
    assert session.draft.at() == before and session.baseline == baseline
    assert session.leave(lambda: "cancel") is False
    assert session.draft.at() == before and session.dirty
    assert session.leave(lambda: "save") is True
    assert session.reload_catalog()[0]["store_id"] == "test"
    session.open("test", lambda: "cancel")
    session.edit(("store_id",), "changed")
    assert not session.leave(lambda: "cancel")
    assert session.leave(lambda: "discard")
    assert session.reload_catalog()[0]["store_id"] == "test"
    session.new("roba", lambda: "discard")
    session.edit(("store_id",), "test")
    assert not session.save()  # Invalid definition, no partial write.
    assert session.dirty and session.original_id is None
    assert session.leave(lambda: "save") is False
    assert session.dirty
    assert session.leave(lambda: "discard")
    assert len(session.reload_catalog()) == 1
    assert ui.StoreSheet.getCommand is not None


@pytest.mark.parametrize(('old','text','expected'), [
    ('old','no quotes needed','no quotes needed'), (1,'2',2), (0.5,'2.25',2.25),
    (True,'false',False), (False,'TRUE',True),
])
def test_atomic_conversion_preserves_type(store_graph, old, text, expected):
    obj, _ = workbench(store_graph[0])
    module = importlib.import_module(obj.runtime.__class__.__module__ + ".session")
    value = module.atomic(old, text)
    assert type(value) is type(old) and value == expected


def test_sheet_keys_are_local_and_non_value_enter_does_not_edit(store_graph, monkeypatch):
    from visidata import Sheet, vd

    create, _, _ = store_graph
    original = {k: Sheet('base').getCommand(vd.prettykeys(k)).execstr
                for k in ('Enter','q','gq','e','z^S')}
    obj, ui = workbench(create)
    s = obj.api.require("create_session")("a")
    sheet = ui.StoreSheet(s)
    sheet.reload()
    # A real draw clears this cache; headless construction has not drawn yet.
    vd.clearCaches()
    assert [column.name for column in sheet.keyCols] == ["key"]
    sheet.cursorVisibleColIndex = sheet.leftVisibleColIndex = 2
    sheet.reload()
    assert sheet.cursorVisibleColIndex == sheet.leftVisibleColIndex == 0
    sheet.parent()
    assert not sheet.exiting
    sheet.newStore()
    assert s.draft is not None
    monkeypatch.setattr(sheet, 'editCell', lambda **kw: 'plain-name')
    sheet.cursorVisibleColIndex = 0
    sheet.enter()
    assert not s.dirty
    sheet.cursorVisibleColIndex = 2
    sheet.enter()
    assert s.dirty and s.draft.at(('store_id',)) == 'plain-name'
    assert sheet.getCommand('cockpit-store-save') is not None
    for k, expr in original.items():
        assert Sheet('unrelated').getCommand(vd.prettykeys(k)).execstr == expr


def test_guards_commit_errors_counts_and_provider_choices(store_graph, api, monkeypatch):
    from visidata import vd

    obj, ui = workbench(store_graph[0])
    s = obj.api.require('create_session')('a')
    catalog = s.catalog
    calls = []
    funcs = {name: catalog.require(name) for name in
             ('list', 'get', 'draft', 'providers_list', 'create', 'update')}
    for name in ('create', 'update'):
        original = funcs[name]

        def counted(*args, _name=name, _call=original):
            calls.append(_name)
            return _call(*args)

        funcs[name] = counted
    s.catalog = api(**funcs)
    sheet = ui.StoreSheet(s)
    sheet.reload()
    monkeypatch.setattr(sheet, 'choose', lambda: 'cancel')
    sheet.newStore()
    for path, value in ((('store_id',), 'a'), (('connection', 'context_id'), 'ctx'),
                        (('connection', 'context_locator'), 'unix:/tmp/not-contacted.sock'),
                        (('connection', 'token'), 'synthetic-only')):
        s.edit(path, value)
    sheet.reload()
    cursor = (sheet.cursorRowIndex, sheet.cursorVisibleColIndex)
    for action in (sheet.parent, sheet.refresh, sheet.newStore, sheet.exitStore):
        action()
        assert s.dirty and (sheet.cursorRowIndex, sheet.cursorVisibleColIndex) == cursor
        assert calls == [] and catalog.require('list')('a') == []
    sheet.saveStore()
    assert calls == ['create'] and not s.dirty
    old = copy.deepcopy(s.baseline)
    s.edit(('store_id',), 'renamed')
    s.edit(('provider',), 'unknown')
    assert not s.save() and s.baseline == old and s.dirty
    assert catalog.require('list')('a')[0]['store_id'] == 'a'
    s.edit(('provider',), 'roba')
    s.catalog.functions['update'] = lambda *args: (_ for _ in ()).throw(OSError('synthetic-only'))
    assert not s.save() and 'synthetic-only' not in s.error and s.baseline == old
    s.catalog.functions['update'] = catalog.require('update')
    assert s.save() and not s.dirty
    s.new('roba', lambda: 'discard')
    s.draft.replace((), copy.deepcopy(s.entries[0]))  # A duplicate complete store.
    assert not s.save() and s.original_id is None
    assert len(catalog.require('list')('a')) == 1
    assert s.leave(lambda: 'discard')
    monkeypatch.setattr(s, 'providers', lambda: ['roba', 'other'])
    monkeypatch.setattr(vd, 'input', lambda *args, **kwargs: 'roba')
    sheet.newStore()
    assert s.draft.at(('provider',)) == 'roba'
    assert catalog.require('list')('a')[0]['store_id'] == 'renamed'
    for old, invalid in ((True, 'yes'), (1, '1.5'), (1., 'nan'), (1., 'inf')):
        atomic = importlib.import_module(obj.runtime.__class__.__module__ + '.session').atomic
        with pytest.raises(ValueError):
            atomic(old, invalid)


def test_local_runtime_retains_draft_after_native_return_and_interrupt(store_graph, monkeypatch):
    import builtins

    obj, ui = workbench(store_graph[0])
    s = obj.api.require('create_session')('a')
    s.new('roba', lambda: 'discard')
    s.edit(('store_id',), 'invalid-new')
    sheet = ui.StoreSheet(s)
    sheet.reload()
    baseline = copy.deepcopy(s.baseline)
    calls = []

    def run(current):
        assert current is sheet and s.dirty and s.baseline == baseline
        calls.append(current)

    answers = iter([KeyboardInterrupt(), 'c', 's', 'd'])

    def prompt(text):
        assert 'Save / Discard / Cancel' in text
        value = next(answers)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(ui.vd, 'run', run)
    monkeypatch.setattr(builtins, 'input', prompt)
    assert ui.run_store(sheet) == 0
    assert len(calls) == 4 and sheet.exiting and s.draft is None
    assert s.reload_catalog() == []


def test_allowlist_reset_gate_and_closed_prompt(store_graph, monkeypatch):
    from visidata import vd

    obj, ui = workbench(store_graph[0])
    keys = importlib.import_module(obj.runtime.__class__.__module__ + '.keymap')
    s = obj.api.require('create_session')('a')
    sheet = ui.StoreSheet(s)
    sheet.reload()
    assert sheet.options.disp_rstatus_fmt == '{sheet.nRows} rows {sheet.modifiedStatus}'
    from visidata import Sheet
    assert Sheet('unrelated-status').options.disp_rstatus_fmt != sheet.options.disp_rstatus_fmt
    before = copy.deepcopy(dict(vd.bindkeys))
    with monkeypatch.context() as m:
        m.setattr(keys, 'version', lambda name: '3.5')
        with pytest.raises(keys.StoreKeymapCompatibilityError, match='VisiData 3.4'):
            keys.configure_store(sheet)
        assert dict(vd.bindkeys) == before
    with monkeypatch.context() as m:
        m.setattr(vd, 'bindkeys', {})
        with pytest.raises(keys.StoreKeymapCompatibilityError):
            keys.configure_store(sheet)
    with monkeypatch.context() as m:
        m.setattr(vd, 'editText', None)
        with pytest.raises(keys.StoreKeymapCompatibilityError):
            keys.configure_store(sheet)
        assert dict(vd.bindkeys) == before
    vd.bindkey('UP067_future_default', 'go-down')
    vd.bindkey('UP067_instance_default', 'go-up', sheet)
    proof = keys.configure_store(sheet)
    assert proof['cleared'] == 0 and len(vd.bindkeys) == 17
    assert set(vd.bindkeys) == {vd.prettykeys(k) for k in keys.BINDINGS}
    assert all(sheet.getCommand(key).longname == command for key, command in
               ((vd.prettykeys(k), v) for k, v in keys.BINDINGS.items()))
    assert not vd.options.disp_menu
    for key in ('i', '-', 'a', 'z^S', 'gq', '^H', '^F', 'UP067_future_default',
                'UP067_instance_default'):
        assert vd.bindkeys._get(vd.prettykeys(key), obj=sheet) is None
    for token in ('', 'bogus', 'w file.toml', 'q | anything', ':w', '!sh'):
        sheet.dispatchStore(token)
        assert s.draft is None and not sheet.exiting and s.reload_catalog() == []
    sheet.dispatchStore(' n ')
    assert s.draft is not None
    s.edit(('store_id',), 'invalid-new')
    sheet.dispatchStore('wq')
    assert s.dirty and not sheet.exiting
    monkeypatch.setattr(sheet, 'choose', lambda: 'cancel')
    for token in ('n', 'r', 'q'):
        old = s.draft.at()
        sheet.dispatchStore(token)
        assert s.draft.at() == old and s.dirty and not sheet.exiting
    removed = []
    monkeypatch.setattr(vd, 'remove', lambda sh: removed.append(sh))
    sheet.dispatchStore('q!')
    assert removed == [sheet] and sheet.exiting and s.draft is None


def test_open_store_only_uses_saved_root_selection_without_saving(store_graph):
    obj, ui = workbench(store_graph[0])
    session = obj.api.require('create_session')('a')
    calls = []
    sheet = ui.StoreSheet(session, opener=lambda ident: calls.append(ident))
    sheet.reload(); sheet.dispatchStore('o')
    assert not calls and 'saved Store' in session.error
    session.new('roba', lambda: 'cancel')
    sheet.reload(); sheet.dispatchStore('o')
    assert not calls and session.draft is not None
    session.edit(('store_id',),'unsaved')
    session.path=('connection',);sheet.reload();sheet.dispatchStore('o')
    assert not calls and session.dirty and 'saved Store' in session.error
    session.leave(lambda:'discard')
    obj.runtime.catalog.require('create')({'store_id':'saved','provider':'roba','connection':{
        'context_id':'offline','context_locator':'unix:/tmp/none.sock','token':'synthetic-open','timeout':1.0}}, 'a')
    sheet.reload();sheet.dispatchStore('o')
    assert calls == ['saved'] and session.draft is None and not session.error
    assert len(session.reload_catalog()) == 1 and not sheet.exiting
    def fail(ident):
        raise RuntimeError('cannot use synthetic-open')
    sheet.opener=fail; sheet.dispatchStore('o')
    assert 'synthetic-open' not in session.error and '[redacted]' in session.error
    assert len(session.reload_catalog()) == 1


def test_removed_root_store_is_rejected_before_workspace_effect(store_graph, monkeypatch, api):
    obj, ui = workbench(store_graph[0])
    catalog = obj.runtime.catalog
    catalog.require('create')({'store_id':'gone','provider':'roba','connection':{
        'context_id':'offline','context_locator':'unix:/tmp/none.sock','token':'synthetic-open','timeout':1.0}}, 'a')
    calls=[]
    obj.runtime.workspace=api(open_store=lambda **values:calls.append(values))
    def local_run(sheet):
        assert sheet.rows[0]['store_id']=='gone'
        catalog.require('remove')('gone','a')
        sheet.dispatchStore('o')
        assert 'does not exist' in sheet.session.error
        assert not sheet.exiting and sheet.session.draft is None
        return 0
    monkeypatch.setattr(ui,'run_store',local_run)
    assert obj.api.require('start')('a')==0
    assert not calls and catalog.require('list')('a')==[]
