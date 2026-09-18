from __future__ import annotations

from pathlib import Path
from textwrap import dedent
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


def test_client_theme_surface_contains_execute_and_four_handlers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    assert {item.id for item in instance.api.functions()} == {
        "execute",
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


def test_client_theme_knot_executes_in_model_order_and_ignores_other_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    focused = _colors(1)
    urgent = _colors(20)

    result = instance.api.require("execute")(
        {"ignored": {"anything": True}, "urgent": urgent, "focused": focused}
    )

    assert result == {"focused": None, "urgent": None}
    assert RecordingConnection.commands == [
        "client.focused " + " ".join(focused.values()),
        "client.urgent " + " ".join(urgent.values()),
    ]
    RecordingConnection.commands = []
    assert instance.api.require("execute")({}) == {}
    assert RecordingConnection.commands == []


def test_client_theme_knot_stops_on_strand_error_before_ipc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    invalid = {**_colors(), "background": "not-a-color"}

    with pytest.raises(Exception) as captured:
        instance.api.require("execute")({"focused": invalid, "urgent": _colors(20)})
    assert type(captured.value).__name__ == "SwayColorError"
    assert RecordingConnection.commands == []


def test_new_knot_owner_reuses_the_spec_with_its_own_client_colors_strand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingConnection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", RecordingConnection)
    module_root = tmp_path / "custom"
    colors_root = module_root / "compositions" / "client_colors"
    colors_root.mkdir(parents=True)
    colors_root.joinpath("composition.toml").write_text(
        dedent(
            """
            [composition]
            id = "client_colors"
            [compositions.base]
            use = "skaldos/sway/theme/client_colors"
            [functions.execute]
            description = "Map one compact custom palette to Sway client colors."
            """
        ).strip()
        + "\n"
    )
    colors_root.joinpath("runtime.py").write_text(
        dedent(
            """
            from collections.abc import Mapping

            class Runtime:
                def __init__(self, *, context, config, base):
                    self.base = base

                def execute(self, value):
                    if not isinstance(value, Mapping):
                        raise ValueError("custom palette must be a mapping")
                    mapped = {
                        "border": value["edge"],
                        "background": value["surface"],
                        "text": value["text"],
                        "indicator": value["accent"],
                        "child_border": value["edge"],
                    }
                    return self.base.require("execute")(mapped)
            """
        ).strip()
        + "\n"
    )
    theme_root = module_root / "compositions" / "client_theme"
    theme_root.mkdir(parents=True)
    theme_root.joinpath("composition.toml").write_text(
        dedent(
            """
            [composition]
            id = "client_theme"
            [compositions.base]
            use = "skaldos/sway/theme/client_theme"
            [compositions.client_colors]
            use = "test/custom/client_colors"
            [compositions.knot]
            use = "dix/norn/knot"
            config = { model = "knot.toml" }
            [functions.set_focused]
            [functions.set_focused_inactive]
            [functions.set_unfocused]
            [functions.set_urgent]
            [functions.execute]
            description = "Execute the custom client theme through the same Knot spec."
            """
        ).strip()
        + "\n"
    )
    theme_root.joinpath("knot.toml").write_text(
        (ROOT / "sway/theme/compositions/client_theme/sway_theme.toml").read_text()
    )
    theme_root.joinpath("runtime.py").write_text(
        dedent(
            """
            class Runtime:
                def __init__(self, *, context, config, base, client_colors, knot):
                    self.base, self.client_colors, self.knot = base, client_colors, knot

                def set_focused(self, value):
                    return self.base.require("set_focused")(value)

                def set_focused_inactive(self, value):
                    return self.base.require("set_focused_inactive")(value)

                def set_unfocused(self, value):
                    return self.base.require("set_unfocused")(value)

                def set_urgent(self, value):
                    return self.base.require("set_urgent")(value)

                def execute(self, value):
                    return self.knot.require("execute")(value)
            """
        ).strip()
        + "\n"
    )

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    modules.load_module(ROOT / "sway/core", module_id="skaldos/sway/core")
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")
    modules.load_module(module_root, module_id="test/custom")
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "custom-theme",
            "test/custom/client_theme",
            {},
            theme_root,
        ),
        owner_scope_id="custom-test",
    )

    focused = {
        "edge": "#010101",
        "surface": "#020202",
        "text": "#030303",
        "accent": "#040404",
    }
    urgent = {
        "edge": "#111111",
        "surface": "#121212",
        "text": "#131313",
        "accent": "#141414",
    }
    result = instance.api.require("execute")({"focused": focused, "urgent": urgent})
    assert result == {"focused": None, "urgent": None}
    assert RecordingConnection.commands == [
        "client.focused #010101 #020202 #030303 #040404 #010101",
        "client.urgent #111111 #121212 #131313 #141414 #111111",
    ]


def test_client_theme_product_has_no_manual_knot_callable_tables() -> None:
    source = (ROOT / "sway/theme/compositions/client_theme/runtime.py").read_text()
    assert 'self.knot.require("execute")(value)' in source
    assert '"client_colors":' not in source
    assert '"set_focused":' not in source
