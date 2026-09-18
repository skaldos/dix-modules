from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import i3ipc
import pytest
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class Reply:
    success = True
    error = ""


class Connection:
    commands: ClassVar[list[str]] = []

    def command(self, value: str) -> list[Reply]:
        self.commands.append(value)
        return [Reply()]


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    Connection.commands = []
    monkeypatch.setattr(i3ipc, "Connection", Connection)
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    modules.load_module(first_party_module_path("dix/cli"), module_id="dix/cli")
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    modules.load_module(ROOT / "sway/core", module_id="skaldos/sway/core")
    modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")
    instance = applications.create_instance(
        ApplicationInstanceSpec("cli", "skaldos/sway/theme/cli", {}, tmp_path),
        owner_scope_id="theme-cli-test",
    )
    try:
        yield instance.api.require("main")
    finally:
        applications.destroy_instance("theme-cli-test", "cli")
        modules.unload_module("skaldos/sway/theme")
        modules.unload_module("skaldos/sway/core")
        modules.unload_module("dix/norn")
        modules.unload_module("dix/cli")


def test_cli_applies_one_explicit_theme_file_without_result_output(
    cli,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    theme = tmp_path / "theme.toml"
    theme.write_text(
        """
[focused]
border = "#010101"
background = "#020202"
text = "#030303"
indicator = "#040404"
child_border = "#050505"

[background]
type = "image"
file = "ignored.png"
mode = "fit"
fallback_color = "#000000"
""".lstrip()
    )

    assert cli(["theme", "apply", "--file", str(theme)]) == 0
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert Connection.commands == ["client.focused #010101 #020202 #030303 #040404 #050505"]


def test_cli_help_exposes_only_theme_apply(cli, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(["--help"]) == 0
    root = capsys.readouterr()
    assert "theme" in root.out
    assert "basic" not in root.out and "windows-list" not in root.out

    assert cli(["theme", "--help"]) == 0
    target = capsys.readouterr()
    assert "apply" in target.out

    assert cli(["theme", "apply", "--help"]) == 0
    apply = capsys.readouterr()
    assert "--file" in apply.out


def test_cli_requires_the_explicit_file_option(cli, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(["theme", "apply"]) == 2
    captured = capsys.readouterr()
    assert "Missing option '--file'" in captured.err
    assert Connection.commands == []
