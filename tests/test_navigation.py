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

    runtime = load_runtime("sway/compositions/basic_nav/runtime.py")(
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
    Runtime = load_runtime("sway/compositions/basic_nav/runtime.py")
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
    Basic = load_runtime("sway/compositions/basic_nav/runtime.py")
    Group = load_runtime("sway/apps/navigation_group/runtime.py")
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
    group = Group(
        context=c,
        config={},
        basic=api(**{x: getattr(basic, x) for x in ("left", "right", "up", "down")}),
        active_members=api(get=lambda: [30, 99]),
        ipc=ipc,
    )
    result = group.right()
    assert result["matched"] is True and result["focused_id"] == 30 and result["stale_ids"] == [99]


def test_navigation_entry_is_route_first_lazy(tmp_path, monkeypatch):
    import importlib.util

    root = Path(__file__).parents[1] / "sway"
    route = tmp_path / "route"
    members = tmp_path / "members"
    route.write_text("basic\n")
    members.write_text("99\n")
    monkeypatch.setenv("SKALDOS_SWAY_NAVIGATION_TARGET_FILE", str(route))
    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE", str(members))

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
    assert mod.main(["left"], root) == 0
    loaded = set(sys.modules) - before
    assert not any("group_navigation" in name or "active_members" in name for name in loaded)
    route.write_text("invalid\n")
    assert mod.main(["left"], root) == 1


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
    Basic = load_runtime("sway/compositions/basic_nav/runtime.py")
    Group = load_runtime("sway/apps/navigation_group/runtime.py")
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
    group = Group(
        context=context,
        config={},
        basic=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        active_members=api(get=lambda: [30]),
        ipc=ipc,
    )
    result = group.right()
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
    Basic = load_runtime("sway/compositions/basic_nav/runtime.py")
    Group = load_runtime("sway/apps/navigation_group/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    group = Group(
        context=context,
        config={},
        basic=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        active_members=api(get=lambda: [30, 40]),
        ipc=ipc,
    )
    result = group.left()
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
    Basic = load_runtime("sway/compositions/basic_nav/runtime.py")
    Group = load_runtime("sway/apps/navigation_group/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    group = Group(
        context=context,
        config={},
        basic=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        active_members=api(get=lambda: [20]),
        ipc=ipc,
    )
    assert group.right()["focused_id"] == 20


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
    Basic = load_runtime("sway/compositions/basic_nav/runtime.py")
    Group = load_runtime("sway/apps/navigation_group/runtime.py")
    context = ApplicationRuntimeContext("x", "x", "x", tmp_path, tmp_path, tmp_path, "x")
    basic = Basic(context=context, config={}, ipc=ipc)
    group = Group(
        context=context,
        config={},
        basic=api(**{name: getattr(basic, name) for name in ("left", "right", "up", "down")}),
        active_members=api(get=lambda: [30]),
        ipc=ipc,
    )
    with pytest.raises(RuntimeError, match="direct focus failed"):
        group.left()
