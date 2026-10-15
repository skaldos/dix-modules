from __future__ import annotations

import os
from pathlib import Path

from dix.core.module import inspect_module

ROOT = Path(__file__).parents[1]
COCKPIT = ROOT / "cockpit"


def test_cockpit_is_one_explicit_external_module_with_privileged_runtime_apps() -> None:
    inspection = inspect_module(COCKPIT, module_id="skaldos/cockpit")
    assert {value.id for value in inspection.composition_definitions} == {
        "skaldos/cockpit/config",
        "skaldos/cockpit/daemon_catalog",
        "skaldos/cockpit/roba_connections",
        "skaldos/cockpit/tmux_workspace",
        "skaldos/cockpit/cockpit_session",
        "skaldos/cockpit/roba_runtime",
    }
    assert {value.id for value in inspection.application_definitions} == {
        "skaldos/cockpit/cli",
        "skaldos/cockpit/control_window",
        "skaldos/cockpit/connection_window",
        "skaldos/cockpit/owner_shell",
        "skaldos/cockpit/runtime_status",
    }


def test_delivery_contains_owned_launchers_helpers_config_and_bilingual_docs() -> None:
    for path in (
        COCKPIT / "integrations/install",
        *(COCKPIT / "integrations/bin").iterdir(),
    ):
        assert path.is_file() and os.access(path, os.X_OK)
    assert {path.name for path in (COCKPIT / "integrations/launchers").iterdir()} == {
        "dix-cockpit.toml",
        "dix-cockpit-owner-shell.toml",
        "dix-cockpit-runtime-status.toml",
    }
    assert (COCKPIT / "integrations/tmux/cockpit.conf").is_file()
    english = (COCKPIT / "README.md").read_text()
    german = (COCKPIT / "README.de.md").read_text()
    for text in (english, german):
        for command in ("dix-cockpit start", "attach", "status", "stop", "reset"):
            assert command in text
        assert "DIX_COCKPIT_RUNTIME_ROOT" in text
        assert "DIX_COCKPIT_STATE_ROOT" in text
        assert "ROBA_CONTROL_TOKEN" in text


def test_privileged_runtime_launcher_templates_do_not_reference_visidata() -> None:
    installer = (COCKPIT / "integrations/install").read_text().lower()
    assert "visidata" not in installer
    for launcher in (COCKPIT / "integrations/launchers").glob("dix-cockpit*.toml"):
        assert "visidata" not in launcher.read_text().lower()


def test_privileged_surface_uses_in_process_roba_and_secret_free_tmux_plans() -> None:
    cli = (COCKPIT / "apps/cli/runtime.py").read_text()
    session = (COCKPIT / "compositions/cockpit_session/runtime.py").read_text()
    runtime = (COCKPIT / "compositions/roba_runtime/runtime.py").read_text()
    assert "subprocess" not in cli + session + runtime
    assert "dix-roba-cli" not in cli + session + runtime
    tmux = (COCKPIT / "compositions/tmux_workspace/runtime.py").read_text()
    assert "control_token" not in tmux and "owner_token" not in tmux
    status = (COCKPIT / "integrations/tmux/cockpit.conf").read_text()
    assert "token" not in status.lower()
