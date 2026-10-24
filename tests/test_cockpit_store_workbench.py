from __future__ import annotations

import copy
import importlib

import pytest


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
    assert sheet.getCommand(vd.prettykeys('z^S')).longname == 'commit-sheet'
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
