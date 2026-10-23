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
