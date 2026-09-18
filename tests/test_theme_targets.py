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


def _load_dependencies(modules: ModuleComponent) -> None:
    modules.load_module(first_party_module_path("dix/cli"), module_id="dix/cli")
    modules.load_module(ROOT / "sway/core", module_id="skaldos/sway/core")
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")


def _composition(tmp_path: Path, composition_id: str):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    _load_dependencies(modules)
    return compositions.create_instance(
        CompositionInstanceSpec(
            composition_id,
            f"skaldos/sway/theme/{composition_id}",
            {},
            tmp_path,
        ),
        owner_scope_id="theme-target-test",
    )


def _client_theme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    RecordingConnection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", RecordingConnection)
    return _composition(tmp_path, "client_theme")


@pytest.mark.parametrize("mode", ["stretch", "fill", "fit", "center", "tile"])
def test_background_strand_normalizes_each_image_mode(tmp_path: Path, mode: str) -> None:
    instance = _composition(tmp_path, "background")
    value = {
        "type": "image",
        "file": "/wallpapers/example.png",
        "mode": mode,
        "fallback_color": "#aBcDeF",
    }

    result = instance.api.require("execute")(value)
    assert result == value
    assert type(result) is dict
    assert result is not value


def test_background_strand_normalizes_color_variant(tmp_path: Path) -> None:
    instance = _composition(tmp_path, "background")
    value = {"type": "color", "color": "#A1b2C3"}

    result = instance.api.require("execute")(value)
    assert result == value
    assert type(result) is dict
    assert result is not value


@pytest.mark.parametrize(
    "value,match",
    [
        ([], "strand input value is incompatible"),
        ({}, "type must be exactly"),
        ({"type": "unknown"}, "type must be exactly"),
        (
            {"type": "image", "file": "/wall.png", "mode": "fit"},
            "missing fields",
        ),
        (
            {
                "type": "image",
                "file": "/wall.png",
                "mode": "fit",
                "fallback_color": "#000000",
                "color": "#111111",
            },
            "additional fields",
        ),
        (
            {
                "type": "image",
                "file": "",
                "mode": "fit",
                "fallback_color": "#000000",
            },
            "absolute path",
        ),
        (
            {
                "type": "image",
                "file": 1,
                "mode": "fit",
                "fallback_color": "#000000",
            },
            "absolute path",
        ),
        (
            {
                "type": "image",
                "file": "relative.png",
                "mode": "fit",
                "fallback_color": "#000000",
            },
            "absolute path",
        ),
        (
            {
                "type": "image",
                "file": "/wall.png",
                "mode": "scale",
                "fallback_color": "#000000",
            },
            "mode must be one of",
        ),
        (
            {
                "type": "image",
                "file": "/wall.png",
                "mode": 1,
                "fallback_color": "#000000",
            },
            "mode must be one of",
        ),
        (
            {
                "type": "image",
                "file": "/wall.png",
                "mode": "fit",
                "fallback_color": "#000000ff",
            },
            "#RRGGBB",
        ),
        ({"type": "color"}, "missing fields"),
        ({"type": "color", "color": "#000000", "mode": "fit"}, "additional fields"),
        ({"type": "color", "color": "#000000ff"}, "#RRGGBB"),
        ({"type": "color", "color": 1}, "#RRGGBB"),
    ],
)
def test_background_strand_rejects_invalid_variants(
    tmp_path: Path,
    value: object,
    match: str,
) -> None:
    instance = _composition(tmp_path, "background")
    with pytest.raises(Exception, match=match):
        instance.api.require("execute")(value)


def test_background_handler_applies_image_and_color_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    image = {
        "type": "image",
        "file": "/wallpapers/example.png",
        "mode": "fill",
        "fallback_color": "#010203",
    }
    color = {"type": "color", "color": "#AABBCC"}

    assert instance.api.require("set_background")(image) is None
    assert instance.api.require("set_background")(color) is None
    assert RecordingConnection.commands == [
        "output * bg /wallpapers/example.png fill #010203",
        "output * bg #AABBCC solid_color",
    ]


def test_background_handler_quotes_one_unsafe_path_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    value = {
        "type": "image",
        "file": '/wall papers/a; output HDMI-A-1 disable "quoted".png',
        "mode": "fit",
        "fallback_color": "#000000",
    }

    assert instance.api.require("set_background")(value) is None
    assert RecordingConnection.commands == [
        'output * bg "/wall papers/a; output HDMI-A-1 disable \\"quoted\\".png" fit #000000'
    ]


def test_background_handler_revalidates_direct_input_before_ipc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = _client_theme(tmp_path, monkeypatch)
    invalid = {
        "type": "image",
        "file": "relative.png",
        "mode": "fit",
        "fallback_color": "#000000",
    }

    with pytest.raises(Exception, match="absolute path"):
        instance.api.require("set_background")(invalid)
    assert RecordingConnection.commands == []
