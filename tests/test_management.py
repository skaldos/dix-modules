from __future__ import annotations

import inspect
from pathlib import Path

from dix.core.application import (
    ApplicationApi,
    ApplicationFunctionDescriptor,
    ApplicationRuntimeContext,
)


def api():
    def create(*, group: str) -> None:
        pass

    def add(*, group: str) -> bool:
        return True

    def remove(*, group: str) -> bool:
        return True

    def clear(*, group: str) -> bool:
        return True

    def show(*, group: str) -> list[int]:
        return [34]

    def list_() -> dict[str, list[int]]:
        return {"work": [34]}

    def memberships() -> list[str]:
        return ["work"]

    def select(*, group: str) -> bool:
        return True

    def deactivate() -> bool:
        return True

    def current() -> str:
        return "work"

    values = {
        "create": create,
        "add": add,
        "remove": remove,
        "clear": clear,
        "show": show,
        "list": list_,
        "memberships": memberships,
        "select": select,
        "deactivate": deactivate,
        "current": current,
    }
    desc = {
        k: ApplicationFunctionDescriptor(
            id=k,
            application_id="skaldos/sway/groups",
            source="local",
            origin=None,
            signature=inspect.signature(v),
            return_annotation=inspect.signature(v).return_annotation,
            docstring=k,
        )
        for k, v in values.items()
    }
    return ApplicationApi(values, desc)


def test_cli_projects_complete_group_surface(load_runtime, tmp_path):
    Runtime = load_runtime("sway/apps/cli/runtime.py")
    captured = {}

    class Typer:
        def require(self, name):
            def invoke(**kw):
                captured.update(kw)
                return 0

            return invoke

    c = ApplicationRuntimeContext(
        instance_id="x",
        application_id="x",
        module_id="x",
        module_root=tmp_path,
        application_root=tmp_path,
        config_base_dir=tmp_path,
        owner_scope_id="x",
    )
    assert Runtime(context=c, config={}, typer=Typer(), groups=api(), themes=api()).main([]) == 0
    assert {x.id for x in captured["targets"]["group"].functions()} == {
        "create",
        "add",
        "remove",
        "clear",
        "show",
        "list",
        "memberships",
        "select",
        "deactivate",
        "current",
    }


def test_integrations_are_not_definitions():
    root = Path(__file__).parents[1] / "sway"
    assert not list((root / "integrations").rglob("app.toml"))
    assert not list((root / "integrations").rglob("composition.toml"))
