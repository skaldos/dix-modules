from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _runtime(load_runtime, api, tmp_path, monkeypatch, config=None):
    monkeypatch.delenv("SKALDOS_SWAY_THEME_DIR", raising=False)
    runtime = load_runtime("sway/compositions/theme_files/runtime.py")
    return runtime(context=None, config=config or {"theme_dir": str(tmp_path / "themes")})


def _complete(background: str = 'type = "solid_color"\ncolor = "#102030"\n') -> str:
    value = '''[clients.focused]
border = "#010203"
background = "#04050678"
text = "#070809"
indicator = "#0A0B0C"
child_border = "#0D0E0F"

[clients.focused_inactive]
border = "#111213"
background = "#141516"
text = "#171819"
indicator = "#1A1B1C"
child_border = "#1D1E1F"

[clients.focused_tab_title]
border = "#212223"
background = "#242526"
text = "#272829"

[clients.unfocused]
border = "#313233"
background = "#343536"
text = "#373839"
indicator = "#3A3B3C"
child_border = "#3D3E3F"

[clients.urgent]
border = "#414243"
background = "#444546"
text = "#474849"
indicator = "#4A4B4C"
child_border = "#4D4E4F"
'''
    return value + (f"[background]\n{background}" if background else "")


def test_create_is_deterministic_complete_and_never_overwrites(
    load_runtime, api, tmp_path, monkeypatch
):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)

    path = Path(instance.create("neutral"))
    first = path.read_bytes()

    assert path == (tmp_path / "themes" / "neutral.toml").resolve()
    assert instance.load("neutral")["background"] == {
        "type": "solid_color",
        "color": "#113344",
    }
    with pytest.raises(FileExistsError):
        instance.create("neutral")
    assert path.read_bytes() == first


def test_list_is_sorted_and_ignores_non_theme_entries(load_runtime, api, tmp_path, monkeypatch):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    (root / "zeta.toml").write_text(_complete())
    (root / "alpha.toml").write_text(_complete())
    (root / "Invalid.toml").write_text(_complete())
    (root / "notes.txt").write_text("ignored")
    (root / "directory.toml").mkdir()

    assert instance.list() == ["alpha", "zeta"]


def test_missing_catalog_lists_empty(load_runtime, api, tmp_path, monkeypatch):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    assert instance.list() == []


def test_load_solid_theme_returns_detached_builtins(load_runtime, api, tmp_path, monkeypatch):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    path = root / "work.toml"
    path.write_text(_complete())

    first = instance.load("work")
    second = instance.load("work")

    assert first["id"] == "work"
    assert first["path"] == str(path.resolve())
    assert first["clients"]["focused"]["background"] == "#04050678"
    assert first["background"] == {"type": "solid_color", "color": "#102030"}
    first["clients"]["focused"]["border"] = "changed"
    assert second["clients"]["focused"]["border"] == "#010203"


def test_load_theme_without_background_preserves_none(load_runtime, api, tmp_path, monkeypatch):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    (root / "plain.toml").write_text(_complete(""))
    assert instance.load("plain")["background"] is None


def test_load_image_resolves_relative_path_without_existence_check(
    load_runtime, api, tmp_path, monkeypatch
):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    (root / "image.toml").write_text(
        _complete(
            'type = "image"\nfile = "wallpapers/not-created.png"\n'
            'mode = "fill"\nfallback_color = "#ABCDEF"\n'
        )
    )

    value = instance.load("image")["background"]

    assert value == {
        "type": "image",
        "file": str((root / "wallpapers" / "not-created.png").resolve()),
        "mode": "fill",
        "fallback_color": "#ABCDEF",
    }


@pytest.mark.parametrize("theme", ["", ".hidden", "../escape", "a/b", "UPPER", "has space"])
def test_theme_id_rejects_aliasing_and_traversal(
    load_runtime, api, tmp_path, monkeypatch, theme
):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="invalid Sway theme ID"):
        instance.load(theme)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text + '\nunknown = "value"\n',
        lambda text: text.replace('[clients.focused]\n', '[clients.focused]\nextra = "#000000"\n'),
        lambda text: text.replace('child_border = "#0D0E0F"\n', "", 1),
        lambda text: text.replace('border = "#010203"', 'border = "red"', 1),
        lambda text: text.replace('border = "#010203"', "border = 1", 1),
        lambda text: text.replace('type = "solid_color"', 'type = "gradient"'),
        lambda text: text.replace('color = "#102030"', 'color = "#102030FF"'),
    ],
)
def test_load_rejects_unknown_missing_and_wrong_typed_data(
    load_runtime, api, tmp_path, monkeypatch, mutation
):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    (root / "broken.toml").write_text(mutation(_complete()))
    with pytest.raises((TypeError, ValueError)):
        instance.load("broken")


@pytest.mark.parametrize(
    "background",
    [
        'type = "image"\nfile = ""\nmode = "fill"\nfallback_color = "#102030"\n',
        'type = "image"\nfile = "x"\nmode = "zoom"\nfallback_color = "#102030"\n',
        'type = "image"\nfile = "x"\nmode = "fill"\nfallback_color = "#12345678"\n',
        'type = "image"\nfile = "x"\nmode = "fill"\n',
    ],
)
def test_load_rejects_invalid_image_background(
    load_runtime, api, tmp_path, monkeypatch, background
):
    instance = _runtime(load_runtime, api, tmp_path, monkeypatch)
    root = tmp_path / "themes"
    root.mkdir()
    (root / "broken.toml").write_text(_complete(background))
    with pytest.raises((TypeError, ValueError)):
        instance.load("broken")


def test_explicit_directory_precedes_config_and_environment(
    load_runtime, api, tmp_path, monkeypatch
):
    monkeypatch.setenv("SKALDOS_SWAY_THEME_DIR", str(tmp_path / "environment"))
    runtime = load_runtime("sway/compositions/theme_files/runtime.py")
    instance = runtime(context=None, config={"theme_dir": str(tmp_path / "config")})

    assert Path(instance.create("from-config")).parent == (tmp_path / "config").resolve()
    assert Path(instance.create("explicit", str(tmp_path / "explicit"))).parent == (
        tmp_path / "explicit"
    ).resolve()
    environment = runtime(context=None, config={})
    assert Path(environment.create("from-env")).parent == (tmp_path / "environment").resolve()


def test_runtime_has_no_sway_ipc_import() -> None:
    source = (ROOT / "sway/compositions/theme_files/runtime.py").read_text()
    imported = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)
    )
    assert not any(name == "i3ipc" or name.startswith("i3ipc.") for name in imported)


def test_manifest_exposes_only_catalog_functions() -> None:
    manifest = (ROOT / "sway/compositions/theme_files/composition.toml").read_text()
    assert [line for line in manifest.splitlines() if line.startswith("[functions.")] == [
        "[functions.create]",
        "[functions.list]",
        "[functions.load]",
    ]
