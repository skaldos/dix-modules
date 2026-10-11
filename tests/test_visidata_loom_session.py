from __future__ import annotations

import copy
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec


class FakeLoom:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: list[tuple[object, str | None]] = []
        self.error: Exception | None = None

    def __call__(self, value: object, object_id: str | None = None) -> object:
        self.calls.append((copy.deepcopy(value), object_id))
        if self.error is not None:
            raise self.error
        return self.results.pop(0)


@pytest.fixture
def workbench(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    modules.load_module(
        Path(__file__).parents[1] / "visidata",
        module_id="skaldos/visidata",
    )
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "workbench", "skaldos/visidata/loom_workbench", {}, tmp_path
        ),
        owner_scope_id="visidata-session-test",
    )
    try:
        yield instance.api
    finally:
        compositions.destroy_instance("visidata-session-test", "workbench")
        modules.unload_module("skaldos/visidata")


def test_seed_duplicate_ids_and_deep_drafts(workbench) -> None:
    provider_result = [
        {"object_id": "same", "description": "first", "value": {"items": [1]}},
        {"object_id": "same", "description": "second", "value": {"items": [2]}},
    ]
    untouched = copy.deepcopy(provider_result)
    loom = FakeLoom([provider_result])
    seed = {"provider": "is data, not a callable"}

    session = workbench.require("create_session")(loom, seed)
    assert loom.calls == [(seed, None)]
    assert [item.description for item in session.references] == ["first", "second"]
    draft = session.inspect(1)
    draft.value["items"].append(3)
    assert draft.dirty
    assert provider_result == untouched
    assert session.references[1].value == {"items": [2]}
    assert len(loom.calls) == 1


def test_explicit_follow_empty_success_and_local_back(workbench) -> None:
    loom = FakeLoom([
        [{"object_id": "follow", "description": "follow it", "value": {"x": 1}}],
        [],
    ])
    session = workbench.require("create_session")(loom, {})
    draft = session.inspect(0)
    draft.value["x"] = 2
    assert session.execute_draft() == ()
    assert loom.calls[-1] == ({"x": 2}, "follow")
    call_count = len(loom.calls)
    assert session.back() is True
    assert len(loom.calls) == call_count
    assert session.draft.value == {"x": 2}
    assert session.draft.dirty


def test_provider_exception_retains_reference_draft_and_history(workbench) -> None:
    loom = FakeLoom([
        [{"object_id": "effect", "description": "effect", "value": {"x": 1}}]
    ])
    session = workbench.require("create_session")(loom, {})
    draft = session.inspect(0)
    draft.value["x"] = 9
    before_references = copy.deepcopy(session.references)
    before_history = copy.deepcopy(session.history)
    loom.error = RuntimeError("provider detail")
    with pytest.raises(RuntimeError, match="provider detail"):
        session.execute_draft()
    assert session.references == before_references
    assert session.draft.value == {"x": 9}
    assert session.history == before_history


@pytest.mark.parametrize(
    "result",
    [
        {},
        [{"object_id": "x", "description": "x"}],
        [{"object_id": "", "description": "x", "value": None}],
        [{"object_id": "x", "description": "", "value": None}],
        [{"object_id": "x", "description": "x", "value": None, "extra": 1}],
    ],
)
def test_closed_reference_contract_rejects_invalid_results(workbench, result) -> None:
    loom = FakeLoom([result])
    with pytest.raises((TypeError, ValueError)):
        workbench.require("create_session")(loom, {})


def test_data_cannot_choose_callable_or_silently_execute(workbench) -> None:
    loom = FakeLoom([
        [{
            "object_id": "inspect",
            "description": "plain data",
            "value": {"callable": "os.system", "provider": "other", "command": "false"},
        }]
    ])
    session = workbench.require("create_session")(loom, {"callable": "builtins.eval"})
    session.inspect(0)
    assert len(loom.calls) == 1
