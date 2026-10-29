from __future__ import annotations

import importlib
import json

from test_cockpit_roba_store import external


def browser_ui(create):
    bound = create("skaldos/cockpit/store_browser")
    ui = importlib.import_module(bound.runtime.__class__.__module__ + ".ui")
    return bound, ui


def test_two_browser_sessions_are_independent_and_errors_keep_other_pane(store_graph):
    create, runtime, owner, conn, _, _, _ = external(store_graph)
    bound, ui = browser_ui(create)
    catalog = bound.runtime.catalog
    catalog.require("create")({"store_id": "data", "provider": "roba", "connection": conn}, "a")
    for name in ("a", "b"):
        assert runtime.require("status")(session=name)["owned"] is True
    left = bound.api.require("create_session")("a")
    right = bound.api.require("create_session")("a")
    a, b = ui.StoreSheet(left, bound.runtime), ui.StoreSheet(right, bound.runtime, side="B")
    a.reload()
    b.reload()
    before = json.dumps(owner.snapshot(), sort_keys=True)
    assert a.rows == b.rows and left.breadcrumb == right.breadcrumb == "/"
    a.openNode()
    assert left.store_id == "data" and right.store_id is None
    assert "data" in left.breadcrumb and conn["token"] not in left.breadcrumb
    left.open(next(n for n in left.rows if n["label"] == "settings"))
    left.open(left.rows[0])
    assert left.breadcrumb == "/data / settings / nested"
    assert right.breadcrumb == "/"
    left.parent()
    assert left.breadcrumb == "/data / settings"
    assert json.dumps(owner.snapshot(), sort_keys=True) == before
    runtime.require("stop")(session="b")
    a.reload()
    assert left.error and a.rows == []
    b.reload()
    assert b.rows[0]["label"] == "data" and not right.error
    a.openNode()  # Empty failed pane is safe, not an IndexError.
    a.rootNode()
    assert left.breadcrumb == "/" and a.rows


def test_provider_choice_local_draft_and_explicit_commit_then_edit_remove(
    store_graph, monkeypatch,
):
    create, _, _ = store_graph
    bound, ui = browser_ui(create)
    vd = ui.vd
    monkeypatch.setattr(vd, "input", lambda *a, **k: "roba")
    monkeypatch.setattr(vd, "confirm", lambda *a, **k: True)
    draft = bound.api.require("new_store")("a", "dix")
    assert draft.draft.value["provider"] == "roba"
    assert bound.runtime.catalog.require("list")("a") == []
    draft.draft.replace(("store_id",), "offline")
    draft.draft.replace(("connection", "context_id"), "missing")
    draft.draft.replace(("connection", "context_locator"), "unix:/tmp/not-a-store.sock")
    draft.draft.replace(("connection", "token"), "local-only-token")
    child = draft.openRow(next(r for r in draft.rows if r["key"] == "connection"))
    child.commitValue()  # Complete draft, even from its nested connection sheet.
    catalog = bound.runtime.catalog
    assert catalog.require("get")("offline", "a")["connection"]["token"] == "local-only-token"
    edited = bound.api.require("edit_store")(
        catalog.require("get")("offline", "a"), session="a", original_id="offline")
    edited.draft.replace(("store_id",), "renamed")
    assert catalog.require("get")("offline", "a")["store_id"] == "offline"
    edited.commitValue()
    browser = bound.api.require("create_session")("a")
    sheet = ui.StoreSheet(browser, bound.runtime)
    sheet.reload()
    sheet.removeStore()
    assert catalog.require("list")("a") == []
    assert "local-only-token" not in sheet.name
    assert "local-only-token" not in browser.safe("oops local-only-token", edited.draft.value)
    assert sheet.getCommand("new-store") and sheet.getCommand("edit-store")
    assert sheet.getCommand("store-parent") and sheet.getCommand("reload-store")


def test_inspect_is_local_display_and_commit_cancel_has_no_effect(store_graph, monkeypatch):
    create, _, _ = store_graph
    bound, ui = browser_ui(create)
    view = ui.InspectSheet("value")
    assert view.rows == [{"value": '"value"'}]
    monkeypatch.setattr(ui.vd, "confirm", lambda *_: False)
    draft = bound.api.require("edit_store")({"arbitrary": []}, session="a")
    draft.commitValue()
    assert bound.runtime.catalog.require("list")("a") == []


def test_distinct_stores_and_depths_have_no_shared_navigation(store_graph):
    create, _, _owner, conn, _, _, _ = external(store_graph)
    bound, ui = browser_ui(create)
    catalog = bound.runtime.catalog
    for name, connection in (("context-store", conn),
                              ("instance-store", {**conn, "instance_id": "one"})):
        catalog.require("create")(
            {"store_id": name, "provider": "roba", "connection": connection}, "a")
    left = bound.api.require("create_session")("a")
    right = bound.api.require("create_session")("a")
    left.reload()
    right.reload()
    left.open(next(n for n in left.rows if n["label"] == "context-store"))
    right.open(next(n for n in right.rows if n["label"] == "instance-store"))
    left.open(next(n for n in left.rows if n["label"] == "settings"))
    left.open(left.rows[0])
    assert left.breadcrumb == "/context-store / settings / nested"
    assert right.breadcrumb == "/instance-store"
    assert right.inspect(right.rows[0]) == "example"
    left.parent()
    left.reload()
    assert right.breadcrumb == "/instance-store"
    right.root()
    assert left.breadcrumb == "/context-store / settings"
    assert right.breadcrumb == "/"
    sheet = ui.StoreSheet(left, bound.runtime)
    assert sheet.getCommand(ui.vd.prettykeys("zB")).longname == "store-parent"
    assert sheet.getCommand(ui.vd.prettykeys("zU")).longname == "store-root"
    assert sheet.getCommand("g/").longname == "search-cols"
    assert sheet.getCommand("h").longname == "go-left"

    for key, name in (("zN", "new-store"), ("zE", "edit-store"),
                      ("zR", "rename-store"), ("zX", "remove-store")):
        assert sheet.getCommand(ui.vd.prettykeys(key)).longname == name


def test_selected_browser_is_rooted_read_only_and_rejects_revision_drift(store_graph):
    from visidata import Sheet

    create, _, owner, conn, _, _, _ = external(store_graph)
    bound, ui = browser_ui(create)
    catalog = bound.runtime.catalog
    for ident, connection in (('context', conn), ('instance', {**conn, 'instance_id': 'one'})):
        catalog.require('create')({'store_id': ident, 'provider': 'roba', 'connection': connection}, 'a')
    before = json.dumps(owner.snapshot(), sort_keys=True)
    context = bound.api.require('create_selected_session')('context', 'a')
    instance = bound.api.require('create_selected_session')('instance', 'a')
    assert context.store_id == 'context' and instance.store_id == 'instance'
    context.reload(); instance.reload()
    assert not context.error and not instance.error
    assert context.breadcrumb == '/context' and instance.breadcrumb == '/instance'
    context.open(next(n for n in context.rows if n['label'] == 'settings'))
    context.open(context.rows[0])
    assert context.breadcrumb == '/context / settings / nested'
    context.parent(); context.root(); context.parent()
    assert context.store_id == 'context' and context.breadcrumb == '/context'
    assert instance.inspect(instance.rows[0]) == 'example'
    sheet = ui.ReadOnlyStoreSheet(context)
    sheet.reload()
    for operation in ('newStore', 'editStore', 'renameStore', 'removeStore'):
        assert not hasattr(sheet, operation)
    for name in ('new-store', 'edit-store', 'rename-store', 'remove-store'):
        assert sheet.getCommand(name) is None
    for key in ('zN', 'zE', 'zR', 'zX'):
        assert sheet.getCommand(ui.vd.prettykeys(key)) == Sheet('unrelated').getCommand(ui.vd.prettykeys(key))
    assert sheet.getCommand('Enter').longname == 'selected-store-enter'
    assert sheet.getCommand('q').longname == 'selected-store-parent'
    definition = catalog.require('get')('context', 'a')
    definition['connection']['timeout'] = .75
    catalog.require('update')('context', definition, 'a')
    assert context.reload() == [] and 'reopen' in context.error
    fresh = bound.api.require('create_selected_session')('context', 'a')
    assert fresh.revision != context.revision and fresh.reload()
    assert instance.reload() and not instance.error
    assert json.dumps(owner.snapshot(), sort_keys=True) == before



def test_selected_header_delegates_to_sheet_without_editor_inheritance(store_graph, monkeypatch):
    from visidata import Sheet

    create, _, _ = store_graph
    bound, ui = browser_ui(create)
    calls=[]
    monkeypatch.setattr(Sheet,'drawColHeader',lambda sheet,*args:calls.append(type(sheet).__name__))
    class Browser:
        store_id='selected'
        breadcrumb='/selected'
        error=''
    for view in (ui.StoreSheet(Browser(),bound.runtime),ui.ReadOnlyStoreSheet(Browser())):
        view._visibleColLayout={0:(0,30)}
        view.drawColHeader(None,0,2,0)
    assert calls==['StoreSheet','ReadOnlyStoreSheet']
