import json
import sys
from pathlib import Path

import pytest
from dix.core.application import ApplicationRuntimeContext


@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
def test_basic_navigation_exposes_native_direction_steps(load_runtime, api, direction):
    current = [10]
    commands = []

    def move(value):
        commands.append(value)
        current[0] = 20

    runtime = load_runtime("sway/nav/compositions/basic_nav/runtime.py")(
        context=None,
        config={},
        ipc=api(focused_con_id=lambda: current[0], focus_direction=move),
    )
    assert getattr(runtime, direction)() == {
        "direction": direction,
        "origin_id": 10,
        "focused_id": 20,
        "changed": True,
    }
    assert commands == [direction]


def test_basic_navigation_enforces_ipc_boundaries(load_runtime, api):
    Runtime = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    unchanged = Runtime(
        context=None,
        config={},
        ipc=api(focused_con_id=lambda: 10, focus_direction=lambda _value: None),
    )
    assert unchanged.left()["changed"] is False

    invalid_id = Runtime(
        context=None,
        config={},
        ipc=api(focused_con_id=lambda: True, focus_direction=lambda _value: None),
    )
    with pytest.raises(TypeError, match="positive integer"):
        invalid_id.left()

    invalid_return = Runtime(
        context=None,
        config={},
        ipc=api(focused_con_id=lambda: 10, focus_direction=lambda _value: False),
    )
    with pytest.raises(TypeError, match="must return None"):
        invalid_return.left()


def test_window_list_navigation_empty_input_is_a_native_noop(load_runtime, api):
    runtime = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")(
        context=None,
        config={},
        basic_nav=api(
            left=lambda: (_ for _ in ()).throw(AssertionError("must not navigate")),
        ),
        ipc=api(
            focused_con_id=lambda: 34,
            live_con_ids=lambda: (_ for _ in ()).throw(AssertionError("must stay lazy")),
        ),
    )
    assert runtime.left() == {
        "direction": "left",
        "origin_id": 34,
        "focused_id": 34,
        "matched": False,
        "restored": True,
        "visited_ids": [34],
        "stale_ids": [],
    }


@pytest.mark.parametrize("window_ids", [True, (1,), [True], [0], [-1], [1, 1]])
def test_window_list_navigation_rejects_invalid_ids(load_runtime, api, window_ids):
    runtime = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")(
        context=None,
        config={},
        basic_nav=api(),
        ipc=api(focused_con_id=lambda: 34),
    )
    with pytest.raises((TypeError, ValueError)):
        runtime.right(window_ids)


def test_navigation_basic_and_group(load_runtime, api, tmp_path):
    current = [10]
    sequence = iter([20, 30])
    commands = []

    def direction(value):
        commands.append(value)
        current[0] = next(sequence)

    ipc = api(
        focused_con_id=lambda: current[0],
        focus_direction=direction,
        focus_con_id=lambda value: current.__setitem__(0, value),
        live_con_ids=lambda: [10, 20, 30],
        navigation_topology=lambda: [
            {"con_id": 1, "parent_id": None, "children": [10, 20, 30], "focus": []},
            {"con_id": 10, "parent_id": 1, "children": [], "focus": []},
            {"con_id": 20, "parent_id": 1, "children": [], "focus": []},
            {"con_id": 30, "parent_id": 1, "children": [], "focus": []},
        ],
    )
    Basic = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    WindowList = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")
    c = ApplicationRuntimeContext(
        instance_id="x",
        application_id="x",
        module_id="x",
        module_root=tmp_path,
        application_root=tmp_path,
        config_base_dir=tmp_path,
        owner_scope_id="x",
    )
    basic = Basic(context=c, config={}, ipc=ipc)
    assert basic.right()["focused_id"] == 20
    current[0] = 10
    sequence = iter([20, 30])
    window_list = WindowList(
        context=c,
        config={},
        basic_nav=api(**{x: getattr(basic, x) for x in ("left", "right", "up", "down")}),
        ipc=ipc,
    )
    result = window_list.right([30, 99])
    assert result["matched"] is True and result["focused_id"] == 30 and result["stale_ids"] == [99]


@pytest.mark.parametrize("direction", ["left", "right", "up", "down"])
def test_nav_application_dispatches_both_strategies(load_runtime, api, direction):
    calls = []

    def basic():
        calls.append(("basic", direction, None))
        return {"direction": direction, "kind": "basic"}

    def windows(window_ids):
        calls.append(("windows-list", direction, list(window_ids)))
        return {"direction": direction, "kind": "windows-list", "window_ids": window_ids}

    runtime = load_runtime("sway/nav/apps/nav/runtime.py")(
        context=None,
        config={},
        basic_nav=api(**{direction: basic}),
        windows_list_nav=api(**{direction: windows}),
    )
    assert getattr(runtime, direction)() == {"direction": direction, "kind": "basic"}
    assert getattr(runtime, direction)("basic", []) == {
        "direction": direction,
        "kind": "basic",
    }
    assert getattr(runtime, direction)("windows-list", [32, 392]) == {
        "direction": direction,
        "kind": "windows-list",
        "window_ids": [32, 392],
    }
    assert getattr(runtime, direction)("windows-list") == {
        "direction": direction,
        "kind": "windows-list",
        "window_ids": [],
    }
    assert calls == [
        ("basic", direction, None),
        ("basic", direction, None),
        ("windows-list", direction, [32, 392]),
        ("windows-list", direction, []),
    ]


def test_nav_application_is_strict_without_fallback(load_runtime, api):
    basic_calls = []
    runtime = load_runtime("sway/nav/apps/nav/runtime.py")(
        context=None,
        config={},
        basic_nav=api(right=lambda: basic_calls.append("right") or {}),
        windows_list_nav=api(right=lambda _ids: {}),
    )
    with pytest.raises(ValueError, match="does not accept"):
        runtime.right("basic", [32])
    with pytest.raises(ValueError, match="unsupported navigation strategy"):
        runtime.right("unknown")
    with pytest.raises(TypeError, match="list or None"):
        runtime.right("basic", ())
    assert basic_calls == []

    invalid = load_runtime("sway/nav/apps/nav/runtime.py")(
        context=None,
        config={},
        basic_nav=api(right=list),
        windows_list_nav=api(right=lambda _ids: {}),
    )
    with pytest.raises(TypeError, match="dictionary"):
        invalid.right()


def test_navigation_entry_is_stateless_and_lazy(tmp_path, monkeypatch, capsys):
    import importlib.util

    root = Path(__file__).parents[1] / "sway/nav"
    class Node:
        id = 34

    class Tree:
        def find_focused(self):
            return Node()

        def leaves(self):
            return [Node()]

    class Reply:
        success = True
        error = None

    class Conn:
        def get_tree(self):
            return Tree()

        def command(self, value):
            return [Reply()]

    import i3ipc

    monkeypatch.setattr(i3ipc, "Connection", Conn)
    spec = importlib.util.spec_from_file_location("nav_entry", root / "navigation_entry.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    before = set(sys.modules)
    assert mod.main(["left", "basic"], root) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["requested"] == value["executed"] == "basic"
    assert value["fallback"] is False
    loaded = set(sys.modules) - before
    assert "skaldos_sway_nav" in loaded
    assert not any("group_navigation" in name or "active_members" in name for name in loaded)
    assert mod.main(["left"], root) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["requested"] == "missing" and value["fallback"] is True


def test_group_navigation_restores_origin_when_no_target(load_runtime, api, tmp_path):
    current = [10]
    sequence = iter([20, 10])
    restored = []

    def direction(_value):
        current[0] = next(sequence)

    def restore(value):
        restored.append(value)
        current[0] = value

    ipc = api(
        focused_con_id=lambda: current[0],
        focus_direction=direction,
        focus_con_id=restore,
        live_con_ids=lambda: [10, 20, 30],
        navigation_topology=lambda: [
            {"con_id": 1, "parent_id": None, "children": [10, 20, 30], "focus": []},
            {"con_id": 10, "parent_id": 1, "children": [], "focus": []},
            {"con_id": 20, "parent_id": 1, "children": [], "focus": []},
            {"con_id": 30, "parent_id": 1, "children": [], "focus": []},
        ],
    )
    Basic = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    WindowList = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")
    context = ApplicationRuntimeContext(
        instance_id="x",
        application_id="x",
        module_id="x",
        module_root=tmp_path,
        application_root=tmp_path,
        config_base_dir=tmp_path,
        owner_scope_id="x",
    )
    basic = Basic(context=context, config={}, ipc=ipc)
    window_list = WindowList(
        context=context,
        config={},
        basic_nav=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        ipc=ipc,
    )
    result = window_list.right([30])
    assert result["matched"] is False and result["restored"] is True
    assert result["focused_id"] == 10 and restored == [10]


def test_group_navigation_resolves_hidden_leaf_in_entered_branch(load_runtime, api, tmp_path):
    current = [10]
    direct = []

    def direction(_value):
        current[0] = 20

    def focus(value):
        direct.append(value)
        current[0] = value

    ipc = api(
        focused_con_id=lambda: current[0],
        focus_direction=direction,
        focus_con_id=focus,
        live_con_ids=lambda: [10, 20, 30, 40],
        navigation_topology=lambda: [
            {"con_id": 1, "parent_id": None, "children": [100, 200], "focus": [100, 200]},
            {"con_id": 100, "parent_id": 1, "children": [110, 40], "focus": [110, 40]},
            {"con_id": 110, "parent_id": 100, "children": [20, 30], "focus": [30, 20]},
            {"con_id": 20, "parent_id": 110, "children": [], "focus": []},
            {"con_id": 30, "parent_id": 110, "children": [], "focus": []},
            {"con_id": 40, "parent_id": 100, "children": [], "focus": []},
            {"con_id": 200, "parent_id": 1, "children": [10], "focus": [10]},
            {"con_id": 10, "parent_id": 200, "children": [], "focus": []},
        ],
    )
    Basic = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    WindowList = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    window_list = WindowList(
        context=context,
        config={},
        basic_nav=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        ipc=ipc,
    )
    result = window_list.left([30, 40])
    assert result["matched"] is True and result["focused_id"] == 30
    assert result["visited_ids"] == [10, 20, 30]
    assert direct == [30]


def test_group_navigation_direct_hit_does_not_read_topology(load_runtime, api, tmp_path):
    current = [10]

    def direction(_value):
        current[0] = 20

    ipc = api(
        focused_con_id=lambda: current[0],
        focus_direction=direction,
        focus_con_id=lambda value: current.__setitem__(0, value),
        live_con_ids=lambda: [10, 20],
        navigation_topology=lambda: (_ for _ in ()).throw(AssertionError("must stay lazy")),
    )
    Basic = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    WindowList = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    window_list = WindowList(
        context=context,
        config={},
        basic_nav=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        ipc=ipc,
    )
    assert window_list.right([20])["focused_id"] == 20


def test_group_navigation_reports_failed_direct_focus(load_runtime, api, tmp_path):
    current = [10]

    def direction(_value):
        current[0] = 20

    ipc = api(
        focused_con_id=lambda: current[0],
        focus_direction=direction,
        focus_con_id=lambda _value: None,
        live_con_ids=lambda: [10, 20, 30],
        navigation_topology=lambda: [
            {"con_id": 1, "parent_id": None, "children": [100, 200], "focus": []},
            {"con_id": 100, "parent_id": 1, "children": [20, 30], "focus": [30]},
            {"con_id": 20, "parent_id": 100, "children": [], "focus": []},
            {"con_id": 30, "parent_id": 100, "children": [], "focus": []},
            {"con_id": 200, "parent_id": 1, "children": [10], "focus": []},
            {"con_id": 10, "parent_id": 200, "children": [], "focus": []},
        ],
    )
    Basic = load_runtime("sway/nav/compositions/basic_nav/runtime.py")
    WindowList = load_runtime("sway/nav/compositions/windows_list_nav/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    window_list = WindowList(
        context=context,
        config={},
        basic_nav=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        ipc=ipc,
    )
    with pytest.raises(RuntimeError, match="direct focus failed"):
        window_list.left([30])
