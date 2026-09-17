from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


class Api:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


def _definition(identifier: str, group: str, theme: str) -> dict[str, str]:
    return {
        "id": identifier,
        "path": f"/definitions/{identifier}.toml",
        "group": group,
        "theme": theme,
    }


def _runtime(load_runtime, definitions, calls, *, groups=None, themes=None):
    Runtime = load_runtime("sway/apps/themed_groups/runtime.py")

    def load_all(path=""):
        calls.append(("files.load_all", path))
        return definitions

    return Runtime(
        context=None,
        config={},
        themed_group_files=Api(load_all=load_all),
        groups=groups or Api(),
        themes=themes or Api(),
    )


def _stateful_groups(calls, initial, current):
    state = {name: list(members) for name, members in initial.items()}
    active = current

    def list_():
        calls.append(("groups.list",))
        return {name: list(members) for name, members in state.items()}

    def current_():
        calls.append(("groups.current",))
        return active

    def deactivate():
        nonlocal active
        calls.append(("groups.deactivate",))
        changed = bool(active)
        active = ""
        return changed

    def clear(group):
        calls.append(("groups.clear", group))
        changed = bool(state[group])
        state[group] = []
        return changed

    def create(group):
        calls.append(("groups.create", group))
        state[group] = []

    def select(group):
        nonlocal active
        calls.append(("groups.select", group))
        changed = active != group
        active = group
        return changed

    return (
        Api(
            list=list_,
            current=current_,
            deactivate=deactivate,
            clear=clear,
            create=create,
            select=select,
        ),
        state,
        lambda: active,
    )


def _themes(calls, *, fail_show="", fail_apply=False):
    def show(theme, theme_dir=""):
        calls.append(("themes.show", theme, theme_dir))
        if theme == fail_show:
            raise ValueError(f"broken theme: {theme}")
        return {"id": theme, "path": f"{theme_dir}/{theme}.toml"}

    def apply(theme, theme_dir="", active_theme_file=""):
        calls.append(("themes.apply", theme, theme_dir, active_theme_file))
        if fail_apply:
            raise RuntimeError("theme IPC failed")
        return {
            "theme": theme,
            "path": f"{theme_dir}/{theme}.toml",
            "background": "image",
        }

    return Api(show=show, apply=apply)


def test_list_projects_a_sorted_detached_mapping_without_other_calls(load_runtime):
    calls = []
    definitions = [
        _definition("first", "zeta", "roba"),
        _definition("second", "alpha", "dix"),
    ]
    runtime = _runtime(load_runtime, definitions, calls)

    first = runtime.list("/catalog")

    assert first == {"alpha": "dix", "zeta": "roba"}
    assert calls == [("files.load_all", "/catalog")]
    first["alpha"] = "changed"
    assert runtime.list("/catalog") == {"alpha": "dix", "zeta": "roba"}


def test_load_preflights_then_only_reconstructs_current_managed_groups(load_runtime):
    calls = []
    definitions = [
        _definition("roba", "roba-dev", "roba"),
        _definition("dix", "dix-dev", "dix"),
        _definition("duplicate-theme", "docs", "dix"),
    ]
    groups, state, active = _stateful_groups(
        calls,
        {
            "dix-dev": [34],
            "docs": [],
            "foreign": [55],
            "removed-definition": [89],
        },
        "dix-dev",
    )
    runtime = _runtime(
        load_runtime, definitions, calls, groups=groups, themes=_themes(calls)
    )

    assert runtime.load("/catalog", "/themes") == {
        "managed_groups": ["dix-dev", "docs", "roba-dev"],
        "created_groups": ["roba-dev"],
        "cleared_groups": ["dix-dev"],
        "deactivated": True,
    }
    assert calls == [
        ("files.load_all", "/catalog"),
        ("themes.show", "dix", "/themes"),
        ("themes.show", "roba", "/themes"),
        ("groups.list",),
        ("groups.current",),
        ("groups.deactivate",),
        ("groups.clear", "dix-dev"),
        ("groups.clear", "docs"),
        ("groups.create", "roba-dev"),
    ]
    assert state == {
        "dix-dev": [],
        "docs": [],
        "foreign": [55],
        "removed-definition": [89],
        "roba-dev": [],
    }
    assert active() == ""

    calls.clear()
    assert runtime.load("/catalog", "/themes") == {
        "managed_groups": ["dix-dev", "docs", "roba-dev"],
        "created_groups": [],
        "cleared_groups": [],
        "deactivated": False,
    }
    assert calls[-3:] == [
        ("groups.clear", "dix-dev"),
        ("groups.clear", "docs"),
        ("groups.clear", "roba-dev"),
    ]


def test_load_empty_catalog_leaves_an_active_foreign_group_untouched(load_runtime):
    calls = []
    groups, state, active = _stateful_groups(calls, {"foreign": [55]}, "foreign")
    runtime = _runtime(load_runtime, [], calls, groups=groups, themes=_themes(calls))

    assert runtime.load() == {
        "managed_groups": [],
        "created_groups": [],
        "cleared_groups": [],
        "deactivated": False,
    }
    assert calls == [("files.load_all", ""), ("groups.list",), ("groups.current",)]
    assert state == {"foreign": [55]}
    assert active() == "foreign"


def test_load_validates_every_theme_before_the_first_group_call(load_runtime):
    calls = []
    definitions = [
        _definition("one", "one", "alpha"),
        _definition("two", "two", "zeta"),
    ]
    groups, _, _ = _stateful_groups(calls, {"one": [1]}, "one")
    runtime = _runtime(
        load_runtime,
        definitions,
        calls,
        groups=groups,
        themes=_themes(calls, fail_show="zeta"),
    )

    with pytest.raises(ValueError, match="broken theme"):
        runtime.load("/catalog", "/themes")

    assert calls == [
        ("files.load_all", "/catalog"),
        ("themes.show", "alpha", "/themes"),
        ("themes.show", "zeta", "/themes"),
    ]


def test_load_checks_dependency_return_types(load_runtime):
    definition = [_definition("work", "work", "dix")]

    runtime = _runtime(
        load_runtime,
        definition,
        [],
        groups=Api(list=lambda: {"work": [True]}, current=lambda: ""),
        themes=Api(show=lambda *_: {}),
    )
    with pytest.raises(TypeError, match="unique positive integer lists"):
        runtime.load()

    runtime = _runtime(
        load_runtime,
        definition,
        [],
        groups=Api(list=lambda: {"work": []}, current=lambda: 3),
        themes=Api(show=lambda *_: {}),
    )
    with pytest.raises(TypeError, match="groups.current"):
        runtime.load()


def test_select_preflights_then_selects_before_applying_theme(load_runtime):
    calls = []
    definitions = [_definition("work-definition", "work group", "dix")]
    groups, _, active = _stateful_groups(calls, {"work group": []}, "")
    runtime = _runtime(
        load_runtime, definitions, calls, groups=groups, themes=_themes(calls)
    )

    result = runtime.select("work group", "/catalog", "/themes", "/state/active")

    assert result == {
        "group": "work group",
        "theme": "dix",
        "group_changed": True,
        "theme_result": {
            "theme": "dix",
            "path": "/themes/dix.toml",
            "background": "image",
        },
    }
    assert calls == [
        ("files.load_all", "/catalog"),
        ("themes.show", "dix", "/themes"),
        ("groups.select", "work group"),
        ("themes.apply", "dix", "/themes", "/state/active"),
    ]
    assert active() == "work group"


def test_select_unknown_group_and_broken_theme_never_mutate_groups(load_runtime):
    definitions = [_definition("work", "work", "dix")]
    calls = []
    groups, _, _ = _stateful_groups(calls, {"work": []}, "")
    runtime = _runtime(
        load_runtime, definitions, calls, groups=groups, themes=_themes(calls)
    )
    with pytest.raises(ValueError, match="unknown themed group"):
        runtime.select("missing")
    assert calls == [("files.load_all", "")]

    calls.clear()
    runtime = _runtime(
        load_runtime,
        definitions,
        calls,
        groups=groups,
        themes=_themes(calls, fail_show="dix"),
    )
    with pytest.raises(ValueError, match="broken theme"):
        runtime.select("work")
    assert calls == [("files.load_all", ""), ("themes.show", "dix", "")]


def test_select_theme_failure_after_group_selection_is_not_rolled_back(load_runtime):
    calls = []
    definitions = [_definition("work", "work", "dix")]
    groups, _, active = _stateful_groups(calls, {"work": []}, "")
    runtime = _runtime(
        load_runtime,
        definitions,
        calls,
        groups=groups,
        themes=_themes(calls, fail_apply=True),
    )

    with pytest.raises(RuntimeError, match="theme IPC failed"):
        runtime.select("work")

    assert active() == "work"
    assert calls == [
        ("files.load_all", ""),
        ("themes.show", "dix", ""),
        ("groups.select", "work"),
        ("themes.apply", "dix", "", ""),
    ]


def test_runtime_imports_no_file_transport_roba_or_sway_capability() -> None:
    path = ROOT / "sway/apps/themed_groups/runtime.py"
    tree = ast.parse(path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    assert not ({"os", "pathlib", "tomllib", "i3ipc", "roba", "dix"} & imports)
