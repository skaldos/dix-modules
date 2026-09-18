from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "window_ids,expected",
    [
        ([], "set $dix_sway_nav windows-list"),
        ([23], "set $dix_sway_nav windows-list 23"),
        ([23, 42], "set $dix_sway_nav windows-list 23 42"),
    ],
)
def test_binding_materializes_one_complete_route(load_runtime, api, window_ids, expected):
    commands: list[str] = []
    runtime = load_runtime("sway/nav/compositions/binding/runtime.py")(
        context=None,
        config={},
        ipc=api(command=lambda value: commands.append(value)),
    )

    runtime.set_windows_list_nav(window_ids)

    assert commands == [expected]


def test_binding_materializes_basic_route(load_runtime, api):
    commands: list[str] = []
    runtime = load_runtime("sway/nav/compositions/binding/runtime.py")(
        context=None,
        config={},
        ipc=api(command=lambda value: commands.append(value)),
    )

    assert runtime.set_basic_nav() is None
    assert commands == ["set $dix_sway_nav basic"]


@pytest.mark.parametrize("window_ids", [None, (), True, [True], [0], [-1], [1, 1]])
def test_binding_rejects_invalid_window_ids_before_ipc(load_runtime, api, window_ids):
    commands: list[str] = []
    runtime = load_runtime("sway/nav/compositions/binding/runtime.py")(
        context=None,
        config={},
        ipc=api(command=lambda value: commands.append(value)),
    )

    with pytest.raises((TypeError, ValueError)):
        runtime.set_windows_list_nav(window_ids)

    assert commands == []


def test_binding_rejects_invalid_ipc_return(load_runtime, api):
    runtime = load_runtime("sway/nav/compositions/binding/runtime.py")(
        context=None,
        config={},
        ipc=api(command=lambda _value: False),
    )

    with pytest.raises(TypeError, match="must return None"):
        runtime.set_basic_nav()


def test_sway_fragment_uses_one_runtime_expanded_route():
    from pathlib import Path

    root = Path(__file__).parents[1]
    value = (root / "sway/nav/integrations/sway/config").read_text()

    assert value.count("set $dix_sway_nav basic") == 1
    assert value.count("$$dix_sway_nav") == 4
    assert "$dix_sway_nav_params" not in value
    assert "active_members" not in value
