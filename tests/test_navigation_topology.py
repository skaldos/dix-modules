from __future__ import annotations

from types import SimpleNamespace

import pytest


def node(value, *, nodes=(), floating=(), focus=()):
    return SimpleNamespace(
        id=value,
        nodes=list(nodes),
        floating_nodes=list(floating),
        focus=list(focus),
    )


def test_ipc_normalizes_regular_and_floating_children(load_runtime, monkeypatch):
    regular = node(2)
    floating = node(3)
    tree = node(1, nodes=[regular], floating=[floating], focus=[3, 2])

    class Connection:
        def get_tree(self):
            return tree

    import i3ipc

    monkeypatch.setattr(i3ipc, "Connection", Connection)
    Runtime = load_runtime("sway/core/compositions/ipc/runtime.py")
    assert Runtime(context=None, config={}).navigation_topology() == [
        {"con_id": 1, "parent_id": None, "children": [2, 3], "focus": [3, 2]},
        {"con_id": 2, "parent_id": 1, "children": [], "focus": []},
        {"con_id": 3, "parent_id": 1, "children": [], "focus": []},
    ]


@pytest.mark.parametrize(
    "topology, message",
    [
        (
            [
                {"con_id": 1, "parent_id": None, "children": [2], "focus": []},
                {"con_id": 1, "parent_id": 1, "children": [], "focus": []},
            ],
            "duplicate",
        ),
        (
            [{"con_id": 1, "parent_id": None, "children": [2], "focus": []}],
            "missing child",
        ),
        (
            [
                {"con_id": 1, "parent_id": None, "children": [2], "focus": []},
                {"con_id": 2, "parent_id": 3, "children": [], "focus": []},
            ],
            "inconsistent",
        ),
        (
            [
                {"con_id": 1, "parent_id": None, "children": [2], "focus": [3]},
                {"con_id": 2, "parent_id": 1, "children": [], "focus": []},
            ],
            "direct children",
        ),
        (
            [
                {"con_id": 1, "parent_id": None, "children": [], "focus": []},
                {"con_id": 2, "parent_id": 3, "children": [3], "focus": []},
                {"con_id": 3, "parent_id": 2, "children": [2], "focus": []},
            ],
            "cycle",
        ),
    ],
)
def test_topology_validation_rejects_invalid_graphs(topology, message):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "sway/core/compositions/ipc/runtime.py"
    spec = importlib.util.spec_from_file_location("topology_validation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.SwayIpcError, match=message):
        module._validate_topology(topology)


def test_ipc_rejects_cycles_in_raw_tree(monkeypatch):
    tree = node(1)
    tree.nodes.append(tree)

    class Connection:
        def get_tree(self):
            return tree

    import i3ipc

    monkeypatch.setattr(i3ipc, "Connection", Connection)
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "sway/core/compositions/ipc/runtime.py"
    spec = importlib.util.spec_from_file_location("cyclic_topology", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.SwayIpcError, match="cycle"):
        module.Runtime(context=None, config={}).navigation_topology()
