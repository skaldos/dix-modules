from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from visidata import vd

ROOT = Path(__file__).parents[1]
UI = ROOT / "cockpit/apps/control_window/ui.py"


def _module():
    spec = importlib.util.spec_from_file_location("cockpit_control_ui_test", UI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_control_sheet_keeps_stopped_running_and_error_rows_and_enter_only_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ui = _module()
    secret = "ephemeral-secret-for-local-ui"
    values = [
        {
            "catalog_id": "stopped",
            "daemon_id": "a",
            "runtime_root": "/tmp/a",
            "logs_root": "/tmp/la",
            "state": "stopped",
            "connection": {"daemon_id": "a"},
            "error": None,
        },
        {
            "catalog_id": "running",
            "daemon_id": "b",
            "runtime_root": "/tmp/b",
            "logs_root": "/tmp/lb",
            "state": "running",
            "connection": {"daemon_id": "b", "control_token": secret},
            "error": None,
        },
        {
            "catalog_id": "broken",
            "daemon_id": "c",
            "runtime_root": "/tmp/c",
            "logs_root": "/tmp/lc",
            "state": "error",
            "connection": None,
            "error": "real resolver error",
        },
    ]
    opened: list[str] = []
    counts: list[int] = []
    monkeypatch.setattr(vd, "status", lambda *_args, **_kwargs: None)
    sheet = ui.ControlSheet(
        load_rows=lambda: values,
        open_connection=lambda catalog_id: opened.append(catalog_id)
        or {"action": "created", "window": "connection-running"},
        update_status=lambda count: counts.append(count),
        session="dix",
        catalog="/tmp/catalog.toml",
        socket="/tmp/dix-cockpit/tmux.sock",
        logo="dix",
    )
    sheet.reload()
    assert [row["state"] for row in sheet.rows] == ["stopped", "running", "error"]
    assert secret in sheet.rows[1]["connection"]
    assert "real resolver error" == sheet.rows[2]["error"]
    assert secret not in sheet.name and "real resolver error" not in sheet.name
    assert counts == [3]
    assert sheet.openRow(sheet.rows[1]) is None
    assert opened == ["running"]
    assert sheet.getCommand("Enter").longname != "execute-loom-reference"
