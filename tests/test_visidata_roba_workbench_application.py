from __future__ import annotations

import importlib
import json
import os
import subprocess
from pathlib import Path

from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.core.composition import CompositionInstanceSpec
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


def test_both_logos_and_nonblocking_branding_contract(tmp_path: Path, monkeypatch) -> None:
    # Load the support module through its composition package, as production does.
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(Path(__file__).parents[1] / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    compositions = registry.require("composition", CompositionComponent)
    instance = compositions.create_instance(
        CompositionInstanceSpec("brand", "skaldos/visidata/loom_workbench", {}, tmp_path),
        owner_scope_id="brand-test",
    )
    branding = importlib.import_module(f"{instance.runtime.__class__.__module__}.branding")
    try:
        for logo in ("dix", "roba"):
            command = branding.logo_command(logo)
            assert command[:7] == ["chafa", "--fill", "block", "-c", "full", "--scale", "0.5"]
            assert Path(command[7]).is_file()
        monkeypatch.setattr(branding.sys.stdin, "isatty", lambda: False)
        assert branding.show_logo("dix") is False
    finally:
        compositions.destroy_instance("brand-test", "brand")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_installer_builds_normal_launcher_in_isolated_delivery_roots(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1] / "visidata"
    dix_root = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
    real_python = Path(os.environ.get("DIX_PYTHON", dix_root / ".venv/bin/python"))
    assert real_python.is_file()
    fake_venv = tmp_path / "venv"
    fake_bin = tmp_path / "tools"
    launchers = tmp_path / "launchers"
    commands = tmp_path / "bin"
    fake_venv.joinpath("bin").mkdir(parents=True)
    fake_bin.mkdir()
    launchers.mkdir()
    commands.mkdir()
    fake_venv.joinpath("bin/python").write_text(
        f"#!/bin/sh\nexec {real_python} \"$@\"\n"
    )
    fake_venv.joinpath("bin/python").chmod(0o755)
    uv_log = tmp_path / "uv.log"
    fake_bin.joinpath("uv").write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {uv_log}\n"
    )
    fake_bin.joinpath("uv").chmod(0o755)
    old = commands / "skaldos-workbench"
    old.write_text("legacy")
    env_file = tmp_path / "dix.env"
    env_file.write_text(
        f"DIX_SOURCE_ROOT={dix_root}\n"
        f"DIX_VENV={fake_venv}\n"
        f"DIX_LAUNCHERS={launchers}\n"
        f"DIX_BIN={commands}\n"
    )
    environment = {
        **os.environ,
        "DIX_ENV": str(env_file),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    installed = subprocess.run(
        [str(root / "integrations/install")],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert installed.returncode == 0, installed.stderr
    assert (launchers / "dix-roba-workbench.py").is_file()
    assert (commands / "dix-roba-workbench").is_file()
    assert not old.exists()
    assert "pip install --python" in uv_log.read_text()
    help_result = subprocess.run(
        [str(fake_venv / "bin/python"), str(launchers / "dix-roba-workbench.py"), "--help"],
        cwd=dix_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "--seed" in help_result.stdout and "--logo" in help_result.stdout
