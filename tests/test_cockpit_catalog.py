from __future__ import annotations

from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


@pytest.fixture
def catalog_api(tmp_path: Path):
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
        CompositionInstanceSpec("catalog", "skaldos/cockpit/daemon_catalog", {}, tmp_path),
        owner_scope_id="cockpit-catalog-test",
    )
    try:
        yield instance.api
    finally:
        compositions.destroy_instance("cockpit-catalog-test", "catalog")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_catalog_preserves_order_and_resolves_relative_and_home_paths(
    catalog_api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    path = tmp_path / "config" / "daemons.toml"
    path.parent.mkdir()
    path.write_text(
        """
[daemons.second]
daemon_id = "daemon-b"
runtime_root = "runtime/b"
logs_root = "~/logs/b"

[daemons.first]
daemon_id = "daemon-a"
runtime_root = "runtime/a"
logs_root = "logs/a"
timeout = 2.5
""".strip()
    )
    entries = catalog_api.require("load")(path)
    assert [entry["catalog_id"] for entry in entries] == ["second", "first"]
    assert entries[0] == {
        "catalog_id": "second",
        "daemon_id": "daemon-b",
        "runtime_root": str((path.parent / "runtime/b").resolve()),
        "logs_root": str((tmp_path / "home/logs/b").resolve()),
        "timeout": 5.0,
    }
    assert entries[1]["timeout"] == 2.5


@pytest.mark.parametrize(
    "document, message",
    (
        ("[other]\nx = 1\n", "exactly one"),
        ("[daemons]\n", "at least one"),
        (
            '[daemons.a]\ndaemon_id="a"\nruntime_root="r"\nlogs_root="l"\nextra=1\n',
            "unknown fields",
        ),
        ('[daemons.a]\ndaemon_id=""\nruntime_root="r"\nlogs_root="l"\n', "non-empty"),
        ('[daemons.a]\ndaemon_id="a"\nruntime_root="r"\nlogs_root="l"\ntimeout=true\n', "number"),
        (
            '[daemons.a]\ndaemon_id="a"\nruntime_root="r"\nlogs_root="l"\n'
            + "[daemons.a]\ntimeout=1\n",
            "invalid daemon catalog",
        ),
    ),
)
def test_catalog_rejects_ambiguous_or_invalid_documents(
    catalog_api, tmp_path: Path, document: str, message: str
) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text(document)
    with pytest.raises(ValueError, match=message):
        catalog_api.require("load")(path)


def test_config_uses_xdg_defaults_without_creating_files(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    instance = compositions.create_instance(
        CompositionInstanceSpec("config", "skaldos/cockpit/config", {}, tmp_path),
        owner_scope_id="cockpit-config-test",
    )
    try:
        assert instance.api.require("defaults")() == {
            "catalog_path": str(tmp_path / "cfg/skaldos/cockpit/daemons.toml"),
            "runtime_root": str(tmp_path / "run/dix-cockpit"),
            "state_root": str(tmp_path / "state/skaldos/cockpit"),
        }
        assert not (tmp_path / "cfg").exists()
        assert not (tmp_path / "run").exists()
        assert not (tmp_path / "state").exists()
    finally:
        compositions.destroy_instance("cockpit-config-test", "config")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
