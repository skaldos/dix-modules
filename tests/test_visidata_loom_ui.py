from __future__ import annotations

import copy
import importlib
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path


class FakeLoom:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None]] = []
        self.result: object = [
            {
                "object_id": "same",
                "description": "editable",
                "value": {"scalar": 1, "tree": {"old": True}, "native": (1, 2)},
            }
        ]
        self.error: Exception | None = None

    def __call__(self, value: object, object_id: str | None = None) -> object:
        self.calls.append((copy.deepcopy(value), object_id))
        if self.error:
            raise self.error
        return copy.deepcopy(self.result)


@pytest.fixture
def ui_runtime(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(Path(__file__).parents[1] / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    instance = compositions.create_instance(
        CompositionInstanceSpec("workbench", "skaldos/visidata/loom_workbench", {}, tmp_path),
        owner_scope_id="visidata-ui-test",
    )
    ui = importlib.import_module(f"{instance.runtime.__class__.__module__}.ui")
    try:
        yield instance.api, ui
    finally:
        compositions.destroy_instance("visidata-ui-test", "workbench")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_reference_enter_only_inspects_and_duplicate_rows_remain_complete(ui_runtime) -> None:
    api, ui = ui_runtime
    loom = FakeLoom()
    loom.result = [
        {"object_id": "same", "description": "one", "value": {"n": 1}},
        {"object_id": "same", "description": "two", "value": {"n": 2}},
    ]
    session = api.require("create_session")(loom, {})
    sheet = ui.ReferenceSheet(session)
    sheet.reload()
    child = sheet.openRow(sheet.rows[1])
    assert child.draft.value == {"n": 2}
    assert len(loom.calls) == 1
    assert sheet.getCommand("execute-loom-reference") is not None
    assert ui.vd.prettykeys("^J") == "Shift+Enter"
    assert sheet.getCommand("Shift+Enter").longname == "execute-loom-reference"
    command_e = sheet.getCommand("E")
    assert command_e is None or command_e.longname != "execute-loom-reference"


def test_old_reference_sheet_uses_its_snapshot_after_other_branch_executes(
    ui_runtime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from visidata import vd

    api, ui = ui_runtime
    loom = FakeLoom()
    loom.result = [
        {"object_id": "store", "description": "old store", "value": {"old": 1}},
        {"object_id": "data", "description": "old data", "value": {"old": 2}},
    ]
    session = api.require("create_session")(loom, {})
    root = ui.ReferenceSheet(session, confirm_execute=False)
    root.reload()

    store = root.openRow(root.rows[0])
    loom.result = [
        {"object_id": "wrong-zero", "description": "new zero", "value": {"new": 0}},
        {"object_id": "wrong-one", "description": "new one", "value": {"new": 1}},
    ]
    session.execute_draft(store.draft)
    reopened_store = root.openRow(root.rows[0])
    assert reopened_store.draft.reference.object_id == "store"
    assert reopened_store.draft.value == {"old": 1}

    loom.result = [
        {"object_id": "only-new", "description": "one result", "value": {"new": True}},
    ]
    session.execute_draft(reopened_store.draft)
    reopened_data = root.openRow(root.rows[1])
    assert reopened_data.draft.reference.object_id == "data"
    assert reopened_data.draft.value == {"old": 2}

    def unexpected_confirm(*args, **kwargs):
        raise AssertionError("no-confirm mode must not ask")

    monkeypatch.setattr(vd, "confirm", unexpected_confirm)
    monkeypatch.setattr(vd, "push", lambda *args, **kwargs: None)
    loom.result = []
    root.executeRow(root.rows[1])
    assert loom.calls[-1] == ({"old": 2}, "data")


def test_scalar_and_complete_subtree_are_local_until_confirmed_execute(
    ui_runtime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from visidata import vd

    api, ui = ui_runtime
    loom = FakeLoom()
    session = api.require("create_session")(loom, {})
    root = ui.ReferenceSheet(session)
    assert root.confirm_execute is True
    root.reload()
    draft_sheet = root.openRow(root.rows[0])
    monkeypatch.setattr(vd, "status", lambda *args, **kwargs: None)
    values = iter(("2", '{"new":[1,2]}'))
    monkeypatch.setattr(vd, "input", lambda *args, **kwargs: next(values))
    draft_sheet.editScalar(draft_sheet.rows[0])
    draft_sheet.replaceSubtree(draft_sheet.rows[1])
    assert session.draft.value["scalar"] == 2
    assert session.draft.value["tree"] == {"new": [1, 2]}
    assert len(loom.calls) == 1

    monkeypatch.setattr(vd, "confirm", lambda *args, **kwargs: False)
    monkeypatch.setattr(vd, "push", lambda *args, **kwargs: None)
    draft_sheet.executeDraft()
    assert len(loom.calls) == 1

    loom.result = []
    monkeypatch.setattr(vd, "confirm", lambda *args, **kwargs: True)
    draft_sheet.executeDraft()
    assert len(loom.calls) == 2
    assert loom.calls[-1][1] == "same"
    assert session.references == ()


def test_native_value_is_visible_but_not_lossily_replaced(
    ui_runtime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from visidata import vd

    api, ui = ui_runtime
    session = api.require("create_session")(FakeLoom(), {})
    root = ui.ReferenceSheet(session)
    root.reload()
    draft = root.openRow(root.rows[0])

    def fail(message: str):
        raise ValueError(message)

    monkeypatch.setattr(vd, "fail", fail)
    with pytest.raises(ValueError, match="not losslessly"):
        draft.replaceSubtree(draft.rows[2])
    assert session.draft.value["native"] == (1, 2)


def test_provider_error_remains_visible_and_keeps_draft(
    ui_runtime, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from visidata import vd

    api, ui = ui_runtime
    loom = FakeLoom()
    session = api.require("create_session")(loom, {})
    root = ui.ReferenceSheet(session)
    root.reload()
    draft = root.openRow(root.rows[0])
    draft.draft.value["scalar"] = 9
    loom.error = RuntimeError("visible provider error")
    monkeypatch.setattr(vd, "confirm", lambda *args, **kwargs: True)

    def fail(message: str):
        raise ValueError(message)

    monkeypatch.setattr(vd, "fail", fail)
    with pytest.raises(ValueError, match="RuntimeError: visible provider error"):
        draft.executeDraft()
    assert session.draft.value["scalar"] == 9
