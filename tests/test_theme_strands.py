from __future__ import annotations

from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


def _color(tmp_path: Path):
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    compositions = registry.require("composition", CompositionComponent)
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    loaded = modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")
    instance = compositions.create_instance(
        CompositionInstanceSpec("color", "skaldos/sway/theme/color", {}, tmp_path),
        owner_scope_id="theme-test",
    )
    return loaded, instance


def test_color_strand_runs_in_real_composed_graph(tmp_path: Path) -> None:
    loaded, instance = _color(tmp_path)

    assert tuple(loaded.applications) == ()
    assert tuple(loaded.compositions) == ("skaldos/sway/theme/color",)
    assert {item.id for item in instance.api.functions()} == {"execute"}
    execute = instance.api.require("execute")
    for color in ("#012345", "#aBcDeF", "#01234567", "#ABCDEFab"):
        assert execute(color) == color


def test_color_keeps_structural_and_domain_errors_separate(tmp_path: Path) -> None:
    _, instance = _color(tmp_path)
    execute = instance.api.require("execute")

    with pytest.raises(Exception) as structural:
        execute(123)
    assert type(structural.value).__name__ == "StrandInputValueError"
    assert "input" in str(structural.value)

    for invalid in ("red", "#fff", "#1234", "#12345g", " #123456", "#123456 "):
        with pytest.raises(Exception) as domain:
            execute(invalid)
        assert type(domain.value).__name__ == "SwayColorError"
        assert "Sway color" in str(domain.value)
        assert "strand" not in str(domain.value).lower()
