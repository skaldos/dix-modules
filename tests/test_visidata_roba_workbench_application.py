from __future__ import annotations

import importlib
import json
from pathlib import Path

from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path


def test_application_graph_binds_real_roba_loom_and_seed_before_ui(
    tmp_path: Path, monkeypatch,
) -> None:
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(Path(__file__).parents[1] / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    app = applications.create_instance(
        ApplicationInstanceSpec("workbench", "skaldos/visidata/roba_workbench", {}, tmp_path),
        owner_scope_id="visidata-app-test",
    )
    workbench_runtime = next(
        instance.runtime
        for instance in registry.require("composition", CompositionComponent).instances()
        if instance.definition_id == "skaldos/visidata/loom_workbench"
    )
    ui = importlib.import_module(f"{workbench_runtime.__class__.__module__}.ui")
    seen: list[object] = []
    monkeypatch.setattr(ui.vd, "run", lambda sheet: seen.append(sheet))
    monkeypatch.setattr(
        importlib.import_module(f"{workbench_runtime.__class__.__module__}.branding"),
        "show_logo",
        lambda *args, **kwargs: False,
    )
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({
        "daemon_id": "workbench-test",
        "runtime_root": str(tmp_path / "runtime"),
        "logs_root": str(tmp_path / "logs"),
        "timeout": 1.0,
    }))
    try:
        assert app.api.require("main")(["--seed", str(seed), "--logo", "roba"]) == 0
        assert len(seen) == 1
        assert seen[0].logo == "roba"
        seed.write_text("not-json")
        assert app.api.require("main")(["--seed", str(seed)]) == 2
        assert len(seen) == 1
        assert app.api.require("main")(["--help"]) == 0
    finally:
        applications.destroy_instance("visidata-app-test", "workbench")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_launcher_and_installer_use_only_direct_delivery_surface() -> None:
    root = Path(__file__).parents[1] / "visidata"
    launcher = (root / "integrations/launchers/dix-roba-workbench.toml").read_text()
    installer = (root / "integrations/install").read_text()
    wrapper = (root / "integrations/bin/dix-roba-workbench").read_text()
    assert 'application = "skaldos/visidata/roba_workbench"' in launcher
    assert [f'id = "{item}"' in launcher for item in (
        "dix/state", "dix/cli", "dix/norn", "dix/roba", "skaldos/visidata"
    )] == [True] * 5
    assert "DIX_SOURCE_ROOT" in installer
    assert "DIX_VENV" in installer and "DIX_LAUNCHERS" in installer and "DIX_BIN" in installer
    assert "dix-roba-workbench.py" in wrapper
    assert "skaldos-workbench" not in wrapper
    assert not (root / "launch.py").exists()
    assert not list((root / "templates").glob("*"))
