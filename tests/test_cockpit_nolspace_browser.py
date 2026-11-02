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
    for kind in ("array", "object", "nolspace", "vendor"):
        monkeypatch.setattr(ui.vd, "input", lambda *a, kind=kind, **k: kind)
        sheet.dispatch("n")
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
    assert sheet.rows == [] and "No enumerate" in browser.notice
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


def test_complex_values_keep_local_structure_read_only_and_copy_full_native_cell(store_graph, monkeypatch):
    owner, browser, sheet, _ui = selected(store_graph)
    long = "long $literal; " + "z" * 2000 + "\nlast line"
    owner.set("long", long)
    choose(sheet, "values"); sheet.enter()
    calls = track(browser, monkeypatch)
    choose(sheet, "long", col=2); sheet.copy_cell()
    assert calls == [] and "not loaded" in browser.error
    choose(sheet, "long"); sheet.enter()
    assert calls == ["lookup"]
    calls.clear()
    assert len(sheet.cursorRow["value"]) == 120
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
    sheet.dispatch("n"); sheet.dispatch("d")
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
original_version = keymap.version
before = {k: dict(v) for k, v in vd.bindkeys.items()}
keymap.version = lambda name: "0.incompatible"
try:
    keymap.configure_nolspace(sheet)
except keymap.NolspaceKeymapCompatibilityError as exc:
    assert "VisiData 3.4" in str(exc)
else:
    raise AssertionError("incompatible version was accepted")
assert before == dict(vd.bindkeys)
keymap.version = original_version
registry = vd.bindkeys
vd.bindkeys = {}
try:
    keymap.configure_nolspace(sheet)
except keymap.NolspaceKeymapCompatibilityError:
    pass
else:
    raise AssertionError("incompatible registry was accepted")
assert vd.bindkeys == {}
vd.bindkeys = registry
proof = keymap.configure_nolspace(sheet)
assert proof["cleared"] == 0 and len(proof["bindings"]) == 18
assert sheet.getCommand("y").longname == "nolspace-copy"
for key in ("e", "D", "^S", "g/", "x"):
    assert sheet.getCommand(key) is None, key
assert sheet.getCommand(":").longname == "nolspace-prompt"
'''
    result = subprocess.run([__import__("sys").executable, "-c", program, path], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("column", [0, 1, 2])
def test_unloaded_enter_from_any_column_only_loads_once(store_graph, monkeypatch, column):
    _, browser, sheet, _ = selected(store_graph)
    calls = track(browser, monkeypatch)
    choose(sheet, "values", column); sheet.enter()
    assert calls == ["lookup", "enumerate"]
    choose(sheet, "settings", column)
    monkeypatch.setattr(sheet, "editCell", lambda **kw: pytest.fail("lookup also edited"))
    calls.clear(); sheet.enter()
    assert calls == ["lookup"] and not sheet.local
    assert sheet.cursorCol.name == "value"
    sheet.enter()
    assert sheet.local and calls == ["lookup"]


def test_nested_leaf_updates_one_whole_root_and_only_on_success(store_graph, monkeypatch):
    owner, browser, sheet, _ = selected(store_graph)
    original = {"title": "original", "items": [1, False, {"nested": "before"}], "float": 1.5}
    owner.set("complex", original)
    choose(sheet, "values"); sheet.enter()
    choose(sheet, "complex"); sheet.enter(); sheet.enter()
    choose(sheet, "items"); sheet.enter()
    calls = track(browser, monkeypatch)
    from visidata import EscapeException
    def escape(**kw): raise EscapeException()
    monkeypatch.setattr(sheet, "editCell", escape)
    browser.error = "old"; choose(sheet, "0", 2); sheet.enter()
    assert calls == [] and not browser.error and sheet.local.root["value"] == original
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "false")
    sheet.enter()
    assert calls == [] and "valid integer" in browser.error
    assert sheet.local.root["value"] == original
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "42")
    sheet.enter()
    assert calls == ["upsert"] and not browser.error
    choose(sheet, "1", 2); monkeypatch.setattr(sheet, "editCell", lambda **kw: "true"); sheet.enter()
    choose(sheet, "2"); sheet.enter()
    choose(sheet, "nested", 2); monkeypatch.setattr(sheet, "editCell", lambda **kw: "after"); sheet.enter()
    assert calls == ["upsert"] * 3
    expected = {**original, "items": [42, True, {"nested": "after"}]}
    assert owner.get("complex") == expected
    assert sheet.local.root["value"] == expected
    sheet.parent(); sheet.parent()
    choose(sheet, "float", 2); monkeypatch.setattr(sheet, "editCell", lambda **kw: "2"); sheet.enter()
    assert type(sheet.local.root["value"]["float"]) is float
    calls.clear(); confirmed = copy.deepcopy(sheet.local.root)
    def failed(name):
        return lambda *a: (_ for _ in ()).throw(RuntimeError("provider failed"))
    monkeypatch.setattr(browser.provider, "require", failed)
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "3.5"); sheet.enter()
    assert sheet.local.root == confirmed and "provider failed" in browser.error
    # Reload/parent of a local projection is not a read and clears the visible old error.
    sheet.reload(); assert not browser.error
    browser.error = "old"; sheet.parent(); assert not browser.error and not sheet.local
    assert next(r["object"] for r in browser.rows if r["key"] == "complex") == confirmed


def test_readonly_complex_drill_blocks_editor_and_structural_mutation(store_graph, monkeypatch):
    owner, browser, sheet, _ = selected(store_graph, rights={"read": ["instance:one"]})
    owner.with_scope("id:one").set("complex", {"items": [1, {"x": False}]})
    sheet.reload(); choose(sheet, "complex", 1); sheet.enter(); sheet.enter(); sheet.enter()
    calls = track(browser, monkeypatch)
    monkeypatch.setattr(sheet, "editCell", lambda **kw: pytest.fail("read-only editor"))
    choose(sheet, "0", 2); sheet.enter()
    assert "does not offer" in browser.error
    for command in ("n", "d"):
        sheet.dispatch(command); assert "structure is read-only" in browser.error
    assert calls == []


def test_canonical_provider_root_and_path_recovery(store_graph, monkeypatch):
    _, browser, sheet, _ = selected(store_graph)
    choose(sheet, "values"); sheet.enter(); choose(sheet, "settings"); sheet.enter(); sheet.enter()
    choose(sheet, "nested"); sheet.enter(); choose(sheet, "1"); sheet.enter(); choose(sheet, "message", 2)
    calls = []
    canonical = {"name": "settings", "type": "object", "value": {"nested": ["normalized"]}}
    require = browser.provider.require
    def overridden(name):
        if name != "upsert": return require(name)
        def upsert(view, value):
            calls.append(copy.deepcopy(value))
            return copy.deepcopy(canonical)
        return upsert
    monkeypatch.setattr(browser.provider, "require", overridden)
    monkeypatch.setattr(sheet, "editCell", lambda **kw: "attempt")
    sheet.enter()
    assert len(calls) == 1 and calls[0]["value"] == {"nested": ["first", {"message": "attempt"}]}
    assert sheet.local.root == canonical and sheet.local.path == ["nested"]
    assert [r["value"] for r in sheet.rows] == ["normalized"]
    assert next(r["object"] for r in browser.rows if r["key"] == "settings") == canonical


def test_successful_explicit_actions_clear_errors_no_implicit_value_reads(store_graph, monkeypatch):
    owner, browser, sheet, ui = selected(store_graph)
    owner.set("test", 7)
    choose(sheet, "values"); sheet.enter()
    calls = track(browser, monkeypatch)
    choose(sheet, "test", 2); sheet.copy_cell()
    assert "not loaded" in browser.error and calls == []
    sheet.cursorRowIndex = 0; sheet.cursorRowIndex = 1
    assert calls == []
    choose(sheet, "test", 1); sheet.enter(); assert not browser.error
    monkeypatch.setenv("DIX_COCKPIT_CLIPBOARD_COPY", "/unused")
    original = subprocess.run
    def run(args, **kwargs):
        if args == ["/unused"]: return subprocess.CompletedProcess(args, 0)
        return original(args, **kwargs)
    monkeypatch.setattr(subprocess, "run", run)
    browser.error = "stale"; sheet.copy_cell(); assert not browser.error
    assert calls == ["lookup"]
    monkeypatch.setattr(ui.vd, "confirm", lambda *args: False)
    browser.error = "stale"; sheet.dispatch("d"); assert not browser.error
    browser.error = "stale"; sheet.reload(); assert not browser.error
    browser.error = "stale"; sheet.parent(); assert not browser.error
    browser.error = "stale"; sheet.root(); assert not browser.error
