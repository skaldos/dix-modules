from __future__ import annotations

import os
from pathlib import Path

from dix.core.module import inspect_module

ROOT = Path(__file__).parents[1]
COCKPIT = ROOT / "cockpit"


def test_cockpit_is_one_explicit_external_module_with_three_apps() -> None:
    inspection = inspect_module(COCKPIT, module_id="skaldos/cockpit")
    assert {value.id for value in inspection.composition_definitions} == {
        "skaldos/cockpit/config",
        "skaldos/cockpit/daemon_catalog",
        "skaldos/cockpit/roba_connections",
        "skaldos/cockpit/tmux_workspace",
        "skaldos/cockpit/cockpit_session",
    }
    assert {value.id for value in inspection.application_definitions} == {
        "skaldos/cockpit/cli",
        "skaldos/cockpit/control_window",
        "skaldos/cockpit/connection_window",
    }


def test_delivery_contains_owned_launchers_helpers_config_and_bilingual_docs() -> None:
    for path in (
        COCKPIT / "integrations/install",
        *(COCKPIT / "integrations/bin").iterdir(),
    ):
        assert path.is_file() and os.access(path, os.X_OK)
    assert {path.name for path in (COCKPIT / "integrations/launchers").iterdir()} == {
        "dix-cockpit.toml",
        "dix-cockpit-control.toml",
        "dix-cockpit-connection.toml",
    }
    assert (COCKPIT / "integrations/tmux/cockpit.conf").is_file()
    english = (COCKPIT / "README.md").read_text()
    german = (COCKPIT / "README.de.md").read_text()
    for text in (english, german):
        for command in ("dix-cockpit start", "attach", "status", "stop"):
            assert command in text
        assert "Space" in text and "Enter" in text
        assert "DIX_COCKPIT_RUNTIME_ROOT" in text


def test_product_surface_contains_no_cli_subprocess_or_secret_in_window_status_plans() -> None:
    product = {
        path.relative_to(COCKPIT).as_posix(): path.read_text()
        for path in COCKPIT.rglob("*")
        if path.is_file() and path.suffix in {".py", ".toml", ".conf"}
    }
    assert "dix-roba-cli" not in "\n".join(product.values())
    tmux = product["compositions/tmux_workspace/runtime.py"]
    assert "control_token" not in tmux and "owner_token" not in tmux
    status = product["integrations/tmux/cockpit.conf"]
    assert "token" not in status.lower()
