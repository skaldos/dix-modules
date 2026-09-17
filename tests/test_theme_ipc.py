from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _runtime(load_runtime, api, commands, result=None):
    Runtime = load_runtime("sway/compositions/theme_ipc/runtime.py")

    def command(value):
        commands.append(value)
        return result

    return Runtime(context=None, config={}, ipc=api(command=command))


@pytest.mark.parametrize(
    ("method", "arguments", "expected"),
    [
        (
            "set_focused",
            ("#010203", "#040506", "#070809", "#0A0B0C", "#0D0E0F"),
            "client.focused #010203 #040506 #070809 #0A0B0C #0D0E0F",
        ),
        (
            "set_focused_inactive",
            ("#111213", "#141516", "#171819", "#1A1B1C", "#1D1E1F"),
            "client.focused_inactive #111213 #141516 #171819 #1A1B1C #1D1E1F",
        ),
        (
            "set_focused_tab_title",
            ("#212223", "#242526", "#272829"),
            "client.focused_tab_title #212223 #242526 #272829",
        ),
        (
            "set_unfocused",
            ("#313233", "#343536", "#373839", "#3A3B3C", "#3D3E3F"),
            "client.unfocused #313233 #343536 #373839 #3A3B3C #3D3E3F",
        ),
        (
            "set_urgent",
            ("#414243", "#444546", "#474849", "#4A4B4C", "#4D4E4F"),
            "client.urgent #414243 #444546 #474849 #4A4B4C #4D4E4F",
        ),
        (
            "set_background_color",
            ("#102030",),
            "output * bg #102030 solid_color",
        ),
    ],
)
def test_typed_function_emits_exactly_one_command(
    load_runtime, api, method, arguments, expected
):
    commands = []
    runtime = _runtime(load_runtime, api, commands)

    assert getattr(runtime, method)(*arguments) is None
    assert commands == [expected]


def test_background_file_is_one_safely_quoted_argument(load_runtime, api):
    commands = []
    runtime = _runtime(load_runtime, api, commands)
    path = '/absolute/space "quote" \\backslash,comma;semicolon.png'

    assert runtime.set_background_file(path, "fill", "#ABCDEF") is None
    assert commands == [f"output * bg {json.dumps(path)} fill #ABCDEF"]
    encoded = commands[0]
    assert encoded.count(";") == 1
    assert '"quote"' not in encoded


@pytest.mark.parametrize("color", ["red", "#12345", "#123456789", 123])
def test_client_color_validation_happens_before_transport(load_runtime, api, color):
    commands = []
    runtime = _runtime(load_runtime, api, commands)
    with pytest.raises(ValueError, match="client color"):
        runtime.set_focused(color, "#000000", "#000000", "#000000", "#000000")
    assert commands == []


@pytest.mark.parametrize("color", ["#12345678", "blue", "#12345", None])
def test_background_color_is_rgb_only(load_runtime, api, color):
    commands = []
    runtime = _runtime(load_runtime, api, commands)
    with pytest.raises(ValueError, match="background color"):
        runtime.set_background_color(color)
    assert commands == []


@pytest.mark.parametrize("mode", ["zoom", "", 1])
def test_background_file_rejects_unknown_mode_before_transport(load_runtime, api, mode):
    commands = []
    runtime = _runtime(load_runtime, api, commands)
    with pytest.raises(ValueError, match="background mode"):
        runtime.set_background_file("/absolute/image.png", mode, "#010203")
    assert commands == []


@pytest.mark.parametrize("path", ["", "relative.png", "/bad\nname", "/bad\rname", "/bad\x00name"])
def test_background_file_rejects_invalid_path_before_transport(load_runtime, api, path):
    commands = []
    runtime = _runtime(load_runtime, api, commands)
    with pytest.raises(ValueError, match="background path"):
        runtime.set_background_file(path, "fit", "#010203")
    assert commands == []


def test_transport_result_must_be_none(load_runtime, api):
    runtime = _runtime(load_runtime, api, [], result=True)
    with pytest.raises(TypeError, match="must return None"):
        runtime.set_background_color("#010203")


def test_shared_ipc_command_keeps_existing_error_boundary(load_runtime, monkeypatch):
    module_path = ROOT / "sway/compositions/ipc/runtime.py"
    spec = importlib.util.spec_from_file_location("test_theme_shared_ipc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Reply:
        success = True
        error = None

    class Connection:
        def command(self, value):
            calls.append(value)
            return [Reply()]

    monkeypatch.setattr(module.i3ipc, "Connection", Connection)
    runtime = module.Runtime(context=None, config={})
    assert runtime.command("client.focused #000000 #000000 #000000 #000000 #000000") is None
    assert len(calls) == 1
    with pytest.raises(module.SwayIpcError, match="single-line"):
        runtime.command("focus left;\nfocus right")


def test_theme_ipc_has_no_toml_or_theme_file_ownership() -> None:
    path = ROOT / "sway/compositions/theme_ipc/runtime.py"
    tree = ast.parse(path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    source = path.read_text()
    assert "tomllib" not in imports
    assert "theme_dir" not in source
    assert "SKALDOS_SWAY_THEME" not in source


def test_manifest_exposes_exactly_seven_typed_functions() -> None:
    manifest = (ROOT / "sway/compositions/theme_ipc/composition.toml").read_text()
    assert [line for line in manifest.splitlines() if line.startswith("[functions.")] == [
        "[functions.set_focused]",
        "[functions.set_focused_inactive]",
        "[functions.set_focused_tab_title]",
        "[functions.set_unfocused]",
        "[functions.set_urgent]",
        "[functions.set_background_file]",
        "[functions.set_background_color]",
    ]
