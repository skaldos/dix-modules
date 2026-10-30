from __future__ import annotations

import copy
import importlib
import json
import subprocess

import pytest
from test_cockpit_roba_store import external


def selected(store_graph, *, rights=None):
    create, _, owner, conn, _, _, _ = external(store_graph)
    if rights:
        token = owner.token_create(token_id="explicit", **rights)["token"]
        conn = {**conn, "token": token, "instance_id": "one"}
    bound = create("skaldos/cockpit/store_browser")
    catalog = bound.runtime.catalog
    catalog.require("create")({"store_id": "chosen", "provider": "roba", "connection": conn}, "a")
    browser = bound.api.require("create_selected_session")("chosen", "a")
    ui = importlib.import_module(bound.runtime.__class__.__module__ + ".nolspace_ui")
    sheet = ui.NolspaceSheet(browser)
    sheet.reload()
    return owner, browser, sheet, ui


def track(browser, monkeypatch):
    calls = []
    require = browser.provider.require
    def wrapped(name):
        func = require(name)
        def call(*args):
            calls.append(name)
            return func(*args)
        return call
    monkeypatch.setattr(browser.provider, "require", wrapped)
    return calls


def choose(sheet, name, col=0):
    sheet.cursorRowIndex = next(i for i, r in enumerate(sheet.rows) if r["key"] == name)
    sheet.cursorVisibleColIndex = col


def test_browser_lazy_lookup_inline_cancel_and_provider_failure(store_graph, monkeypatch):
    owner, browser, sheet, _ui = selected(store_graph)
    owner.set("atomic", "old")
    calls = track(browser, monkeypatch)
    sheet.reload(); sheet.render()
    assert calls == ["enumerate"]
    assert all(r["type"] == r["value"] == "" for r in sheet.rows)
    choose(sheet, "values"); sheet.enter()
    assert calls == ["enumerate", "lookup", "enumerate"]
    assert browser.breadcrumb == "/chosen / values"
    choose(sheet, "atomic"); sheet.enter()
    assert calls[-1] == "lookup" and sheet.cursorCol.name == "value"
    assert sheet.cursorRow["value"] == "old"
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "new unquoted")
    sheet.enter()
    assert calls[-1] == "upsert" and calls.count("upsert") == 1
    assert owner.get("atomic") == "new unquoted"
    confirmed = copy.deepcopy(sheet.rows)
    # Native Escape raises EscapeException, not an accepted empty string.
    from visidata import EscapeException
    def escape(**kw): raise EscapeException()
    monkeypatch.setattr(sheet, "editCell", escape)
    sheet.enter()
    assert sheet.rows == confirmed and calls.count("upsert") == 1
    def failed(name):
        return lambda *args: (_ for _ in ()).throw(RuntimeError("provider failed"))
    monkeypatch.setattr(browser.provider, "require", failed)
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "not confirmed")
    sheet.enter()
    assert sheet.rows == confirmed and "provider failed" in browser.error
    assert browser.breadcrumb == "/chosen / values"
    assert owner.get("atomic") == "new unquoted"


def test_browser_standard_atomic_creation_strict_parsing_and_delete(store_graph, monkeypatch):
    owner, browser, sheet, ui = selected(store_graph)
    choose(sheet, "values"); sheet.enter()
    calls = track(browser, monkeypatch)
    for kind, raw, expected in [("string", "no quotes", "no quotes"), ("integer", "-2", -2),
                                ("number", "2.5", 2.5), ("boolean", "false", False),
                                ("null", None, None)]:
        answers = iter([kind, "fresh"] + ([raw] if raw is not None else []))
        monkeypatch.setattr(ui.vd, "input", lambda *a, answers=answers, **k: next(answers))
        sheet.dispatch("n")
        assert owner.get("fresh") == expected
    assert calls == ["upsert"] * 5
    choose(sheet, "fresh")
    monkeypatch.setattr(ui.vd, "confirm", lambda *a: False)
    sheet.dispatch("d"); assert calls == ["upsert"] * 5
    monkeypatch.setattr(ui.vd, "confirm", lambda *a: True)
    sheet.dispatch("d"); assert calls == ["upsert"] * 5 + ["delete"]
    assert all(r["key"] != "fresh" for r in sheet.rows)
    for kind, raw in [("integer", "2.0"), ("integer", "True"), ("number", "NaN"),
                      ("number", "true"), ("boolean", "1"), ("null", "none")]:
        with pytest.raises((ValueError, TypeError)):
            ui.parse_atomic(kind, raw)
    for token in ("x", "w", "execute"):
        sheet.dispatch(token)
    assert calls == ["upsert"] * 5 + ["delete"]
    assert "Unknown Nolspace command" in browser.error


def test_browser_actual_read_and_write_only_and_local_complex_inspection(store_graph, monkeypatch):
    _, browser, sheet, _ui = selected(store_graph, rights={"read": ["instance:one"]})
    calls = track(browser, monkeypatch)
    choose(sheet, "name"); sheet.enter()
    count = list(calls)
    monkeypatch.setattr(sheet, "editCell", lambda **k: pytest.fail("read-only editor opened"))
    sheet.enter(); sheet.dispatch("n"); sheet.dispatch("d")
    assert calls == count and "does not offer" in browser.error


def test_write_only_local_result_can_be_deleted_without_lookup(store_graph, monkeypatch):
    owner, browser, sheet, ui = selected(store_graph, rights={"write": ["instance:one"]})
    assert sheet.rows == [] and "No enumerate" in browser.error
    calls = track(browser, monkeypatch)
    answers = iter(["string", "fresh", "write only"])
    monkeypatch.setattr(ui.vd, "input", lambda *a, answers=answers, **k: next(answers))
    sheet.dispatch("n")
    assert sheet.rows[0]["value"] == "write only" and calls == ["upsert"]
    choose(sheet, "fresh"); sheet.enter()
    assert calls == ["upsert"] and "lookup" in browser.error
    monkeypatch.setattr(ui.vd, "confirm", lambda *a: True)
    sheet.dispatch("d")
    assert calls == ["upsert", "delete"] and sheet.rows == []
    assert owner.with_scope("id:one").keys() == ["name"]


def test_complex_values_are_local_read_only_and_copy_uses_full_native_cell(store_graph, monkeypatch):
    owner, browser, sheet, _ui = selected(store_graph)
    long = "long $literal; " + "z" * 2000 + "\nlast line"
    owner.set("long", long)
    choose(sheet, "values"); sheet.enter()
    choose(sheet, "long"); sheet.enter()
    assert len(sheet.cursorRow["value"]) == 120
    calls = track(browser, monkeypatch)
    sent = []
    monkeypatch.setenv("DIX_COCKPIT_CLIPBOARD_COPY", "/absolute/clipboard")
    original_run = subprocess.run
    def copied(argv, **kw):
        if argv != ["/absolute/clipboard"]:
            return original_run(argv, **kw)
        sent.append((argv, kw["input"]))
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(subprocess, "run", copied)
    sheet.copy_cell()
    assert sent == [(["/absolute/clipboard"], long)] and calls == []
    choose(sheet, "settings"); sheet.enter(); sheet.enter()
    assert sheet.local and sheet.rows[0]["key"] == "nested"
    sheet.enter()
    assert sheet.rows[1]["type"] == "object"
    choose(sheet, "1"); sheet.enter()
    assert sheet.rows[0]["value"] == "hello"
    count = list(calls)
    sheet.dispatch("n"); sheet.dispatch("d"); sheet.enter()
    assert calls == count and "read-only" in browser.error
    sheet.parent(); sheet.parent(); sheet.parent()
    assert browser.breadcrumb == "/chosen / values" and not sheet.local
    choose(sheet, "settings"); sheet.cursorVisibleColIndex = 2; sheet.copy_cell()
    assert json.loads(sent[-1][1]) == {"nested": ["first", {"message": "hello"}]}


def test_process_allowlist_is_isolated_and_generic_keymaps_unchanged(store_graph):
    # Actual reset proof runs in a subprocess: never mutate the pytest process's shared VisiData.
    _, _browser, _sheet, ui = selected(store_graph)
    import inspect
    path = inspect.getfile(ui)
    program = '''
import importlib.util, sys
from pathlib import Path
from visidata import vd, Sheet
p = Path(sys.argv[1])
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
ui = load("nolspace_ui", p)
keymap = load("nolspace_keymap", p.with_name("keymap.py"))
assert Sheet("generic").getCommand("/") is not None
class Browser:
    view = None
sheet = ui.NolspaceSheet(Browser())
proof = keymap.configure_nolspace(sheet)
assert proof["cleared"] == 0 and len(proof["bindings"]) == 18
assert sheet.getCommand("y").longname == "nolspace-copy"
for key in ("e", "D", "^S", "g/", "x"):
    assert sheet.getCommand(key) is None, key
assert sheet.getCommand(":").longname == "nolspace-prompt"
'''
    result = subprocess.run([__import__("sys").executable, "-c", program, path], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
