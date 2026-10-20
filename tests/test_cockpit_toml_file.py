from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


@pytest.fixture
def toml_file(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    instance = compositions.create_instance(
        CompositionInstanceSpec("toml", "skaldos/cockpit/toml_file", {}, tmp_path),
        owner_scope_id="cockpit-toml-file-test",
    )
    try:
        yield instance.api
    finally:
        compositions.destroy_instance("cockpit-toml-file-test", "toml")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_loads_explicit_relative_and_absolute_toml_without_metadata(
    toml_file, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "value.toml"
    source.write_text(
        """
name = "dix"
enabled = true
count = 3
ratio = 1.5
special = nan
date = 1979-05-27
time = 07:32:00
stamp = 1979-05-27T07:32:00Z
items = [1, 2]

[nested]
mode = "local"
""".lstrip()
    )
    original = source.read_bytes()
    absolute = toml_file.require("load")(source)
    monkeypatch.chdir(tmp_path)
    relative = toml_file.require("load")(Path("value.toml"))

    assert absolute.keys() == relative.keys()
    assert absolute["date"] == dt.date(1979, 5, 27)
    assert absolute["time"] == dt.time(7, 32)
    assert absolute["stamp"] == dt.datetime(1979, 5, 27, 7, 32, tzinfo=dt.UTC)
    assert absolute["nested"] == {"mode": "local"}
    assert all(key not in absolute for key in ("path", "file", "source", "format"))
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    ("fixture", "message"),
    [
        ("missing", "does not exist"),
        ("directory", "not a regular file"),
        ("utf8", "not valid UTF-8"),
        ("toml", "invalid TOML"),
    ],
)
def test_file_failures_are_visible_before_any_write(
    toml_file, tmp_path: Path, fixture: str, message: str
) -> None:
    source = tmp_path / fixture
    if fixture == "directory":
        source.mkdir()
    elif fixture == "utf8":
        source.write_bytes(b"name = \xff\n")
    elif fixture == "toml":
        source.write_text("[broken")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    with pytest.raises((OSError, ValueError), match=message):
        toml_file.require("load")(source)
    after = {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}
    assert after == before


def test_unreadable_source_is_not_rewritten(toml_file, tmp_path: Path) -> None:
    source = tmp_path / "private.toml"
    source.write_text('name = "hidden"\n')
    original = source.read_bytes()
    source.chmod(0)
    try:
        with pytest.raises(PermissionError):
            toml_file.require("load")(source)
    finally:
        source.chmod(0o600)
    assert source.read_bytes() == original
    assert set(os.listdir(tmp_path)) == {"private.toml"}
