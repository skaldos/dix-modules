from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


def _registry():
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    return registry, modules, loaded


def test_ui_builds_only_non_secret_helper_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    registry, modules, loaded = _registry()
    apps = registry.require("application", ApplicationComponent)
    app = apps.create_instance(
        ApplicationInstanceSpec("ui", "skaldos/cockpit/ui", {}, tmp_path),
        owner_scope_id="cockpit-ui-test",
    )
    try:
        calls: list[dict[str, object]] = []
        app.runtime.session = FakeApi(
            start_master=lambda **values: calls.append(values) or {"running": True}
        )
        monkeypatch.setenv("DIX_BIN", "/opt/dix/bin")
        assert app.api.require("main")(["start", "--session", "private", "--logo", "roba"]) == 0
        assert len(calls) == 1
        values = calls[0]
        assert values["attach"] is True
        assert values["workbench_command"] == [
            "/opt/dix/bin/dix-cockpit-master-workbench",
            "--session",
            "private",
            "--logo",
            "roba",
        ]
        assert "token" not in repr(values).lower()
        assert app.api.require("main")(["--help"]) == 0
        assert "start" in capsys.readouterr().out
    finally:
        apps.destroy_instance("cockpit-ui-test", "ui")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_session_master_orders_start_open_attach_and_rolls_back_only_fresh_resources(
    tmp_path: Path,
) -> None:
    registry, modules, loaded = _registry()
    compositions = registry.require("composition", CompositionComponent)
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "session", "skaldos/cockpit/cockpit_session", {}, tmp_path
        ),
        owner_scope_id="cockpit-master-session-test",
    )
    runtime = instance.runtime
    events: list[str] = []
    try:
        runtime.start = lambda **_values: {
            "running": True,
            "created": {"roba": False, "tmux": False},
            "attached": False,
        }
        runtime.open_master_workbench = (
            lambda **_values: events.append("open")
            or {"session": "dix", "pane_id": "%3", "action": "created"}
        )
        runtime.attach = lambda **_values: events.append("attach") or 0
        result = runtime.start_master(
            shell_command=["shell"],
            status_command=["status"],
            workbench_command=["workbench"],
        )
        assert events == ["open", "attach"]
        assert result["workbench"]["pane_id"] == "%3"
        assert result["attached"] is True

        runtime.start = lambda **_values: {
            "running": True,
            "created": {"roba": True, "tmux": True},
            "attached": False,
        }
        runtime.open_master_workbench = lambda **_values: (_ for _ in ()).throw(
            RuntimeError("pane failed")
        )
        runtime.paths = lambda **_values: {"socket": "/tmp/cockpit/tmux.sock"}
        runtime.tmux = FakeApi(stop=lambda **_values: events.append("tmux-stop") or True)
        runtime.runtime = FakeApi(
            stop=lambda **_values: events.append("roba-stop") or {"stopped": True}
        )
        with pytest.raises(RuntimeError, match="pane failed"):
            runtime.start_master(
                shell_command=["shell"],
                status_command=["status"],
                workbench_command=["workbench"],
                attach=False,
            )
        assert events[-2:] == ["tmux-stop", "roba-stop"]
    finally:
        compositions.destroy_instance("cockpit-master-session-test", "session")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
