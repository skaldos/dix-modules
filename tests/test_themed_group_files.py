from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _write(path: Path, *, group: str = "work", theme: str = "dix") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"group = {group!r}\ntheme = {theme!r}\n", encoding="utf-8")


def test_missing_catalog_and_path_precedence(tmp_path, monkeypatch, load_runtime):
    Runtime = load_runtime("sway/compositions/themed_group_files/runtime.py")
    environment = tmp_path / "environment"
    configured = tmp_path / "configured"
    explicit = tmp_path / "explicit"
    monkeypatch.setenv("SKALDOS_SWAY_THEMED_GROUP_DIR", str(environment))
    _write(environment / "environment.toml")
    _write(configured / "configured.toml")
    _write(explicit / "explicit.toml")

    assert Runtime(context=None, config={}).list() == ["environment"]
    runtime = Runtime(context=None, config={"themed_group_dir": str(configured)})
    assert runtime.list() == ["configured"]
    assert runtime.list(str(explicit)) == ["explicit"]
    assert runtime.list(str(tmp_path / "missing")) == []

    not_directory = tmp_path / "file"
    not_directory.write_text("x")
    with pytest.raises(NotADirectoryError):
        runtime.list(str(not_directory))


def test_list_load_and_load_all_are_deterministic_and_detached(tmp_path, load_runtime):
    Runtime = load_runtime("sway/compositions/themed_group_files/runtime.py")
    root = tmp_path / "catalog"
    _write(root / "z-last.toml", group="Work Group", theme="roba")
    _write(root / "a-first.toml", group="private", theme="dix")
    (root / "notes.txt").write_text("ignored")
    runtime = Runtime(context=None, config={"themed_group_dir": str(root)})

    assert runtime.list() == ["a-first", "z-last"]
    assert runtime.load("z-last") == {
        "id": "z-last",
        "path": str((root / "z-last.toml").resolve()),
        "group": "Work Group",
        "theme": "roba",
    }
    first = runtime.load_all()
    assert [value["id"] for value in first] == ["a-first", "z-last"]
    first[0]["group"] = "changed"
    assert runtime.load_all()[0]["group"] == "private"


@pytest.mark.parametrize(
    "payload, error",
    [
        ("group = 'work'\n", "exactly group and theme"),
        ("group = 'work'\ntheme = 'dix'\nextra = true\n", "exactly group and theme"),
        ("group = 3\ntheme = 'dix'\n", "non-empty string"),
        ("group = ' work'\ntheme = 'dix'\n", "normalized"),
        ("group = 'work '\ntheme = 'dix'\n", "normalized"),
        ('group = "work\\nprivate"\ntheme = "dix"\n', "exactly one line"),
        ("group = 'work'\ntheme = 'DIX'\n", "invalid themed-group theme ID"),
        ("group = 'work'\ntheme = 3\n", "invalid themed-group theme ID"),
        ("group = [\n", "cannot load themed-group definition"),
    ],
)
def test_load_rejects_every_noncanonical_definition(
    payload, error, tmp_path, load_runtime
):
    Runtime = load_runtime("sway/compositions/themed_group_files/runtime.py")
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "broken.toml").write_text(payload)
    runtime = Runtime(context=None, config={"themed_group_dir": str(root)})
    with pytest.raises((TypeError, ValueError), match=error):
        runtime.load("broken")


def test_catalog_rejects_invalid_ids_duplicates_and_escape(tmp_path, load_runtime):
    Runtime = load_runtime("sway/compositions/themed_group_files/runtime.py")
    root = tmp_path / "catalog"
    _write(root / "one.toml", group="same")
    _write(root / "two.toml", group="same", theme="roba")
    runtime = Runtime(context=None, config={"themed_group_dir": str(root)})

    with pytest.raises(ValueError, match="duplicate themed-group group"):
        runtime.load_all()
    with pytest.raises(ValueError, match="invalid themed-group definition ID"):
        runtime.load("../escape")

    _write(root / "Bad.toml", group="other")
    with pytest.raises(ValueError, match="invalid themed-group definition ID"):
        runtime.list()


def test_catalog_rejects_symlink_escape(tmp_path, load_runtime):
    Runtime = load_runtime("sway/compositions/themed_group_files/runtime.py")
    root = tmp_path / "catalog"
    root.mkdir()
    outside = tmp_path / "outside.toml"
    _write(outside)
    (root / "escape.toml").symlink_to(outside)
    runtime = Runtime(context=None, config={"themed_group_dir": str(root)})

    with pytest.raises(ValueError, match="escapes definition directory"):
        runtime.list()


def test_runtime_isolated_from_group_theme_sway_and_roba() -> None:
    path = ROOT / "sway/compositions/themed_group_files/runtime.py"
    tree = ast.parse(path.read_text())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    assert not ({"i3ipc", "roba", "dix"} & imports)
    source = path.read_text()
    for forbidden in ("groups.json", "theme_files", "theme_ipc", "active_theme"):
        assert forbidden not in source
