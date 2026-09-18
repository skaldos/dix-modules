from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import i3ipc
import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class Reply:
    success = True
    error = ""


class RecordingConnection:
    commands: ClassVar[list[str]] = []

    def command(self, value: str) -> list[Reply]:
        self.commands.append(value)
        return [Reply()]


def _client_theme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    RecordingConnection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", RecordingConnection)
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    modules.load_module(ROOT / "sway/core", module_id="skaldos/sway/core")
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")
    return compositions.create_instance(
        CompositionInstanceSpec(
            "client-theme",
            "skaldos/sway/theme/client_theme",
            {},
            tmp_path,
        ),
        owner_scope_id="theme-test",
    )


def _colors(start: int = 1) -> dict[str, str]:
    return {
        "border": f"#{start:06x}",
        "background": f"#{start + 1:06x}",
        "text": f"#{start + 2:06x}",
        "indicator": f"#{start + 3:06x}",
        "child_border": f"#{start + 4:06x}",
    }


@pytest.mark.parametrize(
    "function_id,command_name",
    [
        ("set_focused", "focused"),
        ("set_focused_inactive", "focused_inactive"),
        ("set_unfocused", "unfocused"),
        ("set_urgent", "urgent"),
    ],
)
def test_client_theme_handlers_are_direct_safe_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    function_id: str,
    command_name: str,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    colors = _colors()

    assert instance.api.require(function_id)(colors) is None
    assert RecordingConnection.commands == [
        f"client.{command_name} " + " ".join(colors[field] for field in colors)
    ]


def test_client_theme_initial_surface_contains_only_four_handlers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    assert {item.id for item in instance.api.functions()} == {
        "set_focused",
        "set_focused_inactive",
        "set_unfocused",
        "set_urgent",
    }


@pytest.mark.parametrize(
    "value,match",
    [
        ([], "must be a mapping"),
        ({}, "missing fields"),
        ({**_colors(), "extra": "#000000"}, "additional fields"),
        ({**_colors(), "border": 1}, "invalid Sway client color"),
        ({**_colors(), "border": "#000000; exec evil"}, "invalid Sway client color"),
    ],
)
def test_direct_handlers_reject_unsafe_values_before_ipc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    value: object,
    match: str,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    with pytest.raises(Exception, match=match):
        instance.api.require("set_focused")(value)
    assert RecordingConnection.commands == []
