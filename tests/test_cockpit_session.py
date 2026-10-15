from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import CompositionComponent, ModuleComponent, create_core_component_registry
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


@pytest.fixture
def session_runtime(tmp_path: Path):
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
        CompositionInstanceSpec("session", "skaldos/cockpit/cockpit_session", {}, tmp_path),
        owner_scope_id="cockpit-session-test",
    )
    try:
        yield instance.runtime
    finally:
        compositions.destroy_instance("cockpit-session-test", "session")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def _paths() -> dict[str, str]:
    return {
        "session": "dix",
        "runtime_root": "/tmp/cockpit",
        "state_root": "/tmp/cockpit-state",
        "session_runtime_root": "/tmp/cockpit/sessions/dix",
        "session_state_root": "/tmp/cockpit-state/sessions/dix",
        "owner_file": "/tmp/cockpit/sessions/dix/owner.json",
        "roba_runtime_root": "/tmp/cockpit/sessions/dix/roba",
        "roba_logs_root": "/tmp/cockpit-state/sessions/dix/logs",
        "zsh_root": "/tmp/cockpit-state/sessions/dix/zsh",
        "history_file": "/tmp/cockpit-state/sessions/dix/zsh/history",
        "daemon_socket": "/tmp/cockpit/sessions/dix/roba/daemon.sock",
        "control_socket": "/tmp/cockpit/sessions/dix/roba/control.sock",
    }


def test_session_orders_fresh_reuse_and_daemon_first_stop(session_runtime) -> None:
    events: list[str] = []
    state = {"roba": False, "tmux": False}

    def roba_status(**_values):
        return {
            "state": "running" if state["roba"] else "stopped",
            "running": state["roba"],
            "owned": state["roba"],
        }

    def roba_start(**_values):
        created = not state["roba"]
        state["roba"] = True
        events.append("roba-start")
        return {"created": created}

    def roba_stop(**_values):
        events.append("roba-stop")
        stopped = state["roba"]
        state["roba"] = False
        return {"stopped": stopped}

    def tmux_status(**_values):
        return {
            "running": state["tmux"],
            "owned": state["tmux"],
            "windows": ["control"] if state["tmux"] else [],
        }

    def tmux_start(**_values):
        created = not state["tmux"]
        state["tmux"] = True
        events.append("tmux-start")
        return {"created": created}

    def tmux_stop(**_values):
        events.append("tmux-stop")
        stopped = state["tmux"]
        state["tmux"] = False
        return stopped

    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=roba_status,
        start=roba_start,
        stop=roba_stop,
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=tmux_status,
        start=tmux_start,
        layout_runtime=lambda **_values: events.append("layout"),
        update_runtime_status=lambda **_values: events.append("status-update"),
        attach=lambda **_values: events.append("attach") or 0,
        stop=tmux_stop,
    )

    first = session_runtime.start(shell_command=["shell"], status_command=["status"], attach=False)
    second = session_runtime.start(shell_command=["shell"], status_command=["status"], attach=False)
    assert first["created"] == {"roba": True, "tmux": True}
    assert second["created"] == {"roba": False, "tmux": False}
    assert events.count("layout") == 1
    stopped = session_runtime.stop()
    assert stopped["roba_stopped"] is True and stopped["tmux_stopped"] is True
    assert events[-2:] == ["roba-stop", "tmux-stop"]


def test_session_requires_reset_for_live_tmux_with_missing_daemon(session_runtime) -> None:
    calls: list[str] = []
    state = {"roba": False, "tmux": True}
    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=lambda **_values: {
            "state": "running" if state["roba"] else "stopped",
            "running": state["roba"],
            "owned": state["roba"],
        },
        start=lambda **_values: state.update(roba=True) or {"created": True},
        stop=lambda **_values: (
            calls.append("roba-stop") or state.update(roba=False) or {"stopped": False}
        ),
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=lambda **_values: {
            "running": state["tmux"],
            "owned": state["tmux"],
            "windows": ["control"] if state["tmux"] else [],
        },
        start=lambda **_values: state.update(tmux=True) or {"created": True},
        layout_runtime=lambda **_values: None,
        update_runtime_status=lambda **_values: None,
        attach=lambda **_values: 0,
        stop=lambda **_values: calls.append("tmux-stop") or state.update(tmux=False) or True,
    )

    with pytest.raises(RuntimeError, match="use reset"):
        session_runtime.start(shell_command=["shell"], status_command=["status"], attach=False)
    assert calls == []
    reset = session_runtime.reset(shell_command=["shell"], status_command=["status"], attach=False)
    assert reset["running"] is True
    assert calls == ["roba-stop", "tmux-stop"]


def test_session_rejects_foreign_resources_and_internal_stop(
    session_runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=lambda **_values: {"state": "foreign", "running": True, "owned": False},
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=lambda **_values: {"running": False, "owned": False, "windows": []},
    )
    with pytest.raises(RuntimeError, match="unowned ROBA"):
        session_runtime.stop()

    monkeypatch.setenv("TMUX", "/tmp/tmux,1,0")
    monkeypatch.setenv("DIX_COCKPIT_SESSION", "dix")
    with pytest.raises(RuntimeError, match="detach first"):
        session_runtime.stop()


def test_failed_workspace_creation_rolls_back_only_new_owned_resources(
    session_runtime,
) -> None:
    events: list[str] = []
    state = {"roba": False, "tmux": False}
    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=lambda **_values: {
            "state": "running" if state["roba"] else "stopped",
            "running": state["roba"],
            "owned": state["roba"],
        },
        start=lambda **_values: state.update(roba=True) or {"created": True},
        stop=lambda **_values: (
            events.append("roba-stop") or state.update(roba=False) or {"stopped": True}
        ),
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=lambda **_values: {
            "running": state["tmux"],
            "owned": state["tmux"],
            "windows": [],
        },
        start=lambda **_values: state.update(tmux=True) or {"created": True},
        layout_runtime=lambda **_values: (_ for _ in ()).throw(RuntimeError("layout failed")),
        stop=lambda **_values: events.append("tmux-stop") or state.update(tmux=False) or True,
    )
    with pytest.raises(RuntimeError, match="layout failed"):
        session_runtime.start(shell_command=["shell"], status_command=["status"], attach=False)
    assert events == ["tmux-stop", "roba-stop"]
    assert state == {"roba": False, "tmux": False}


def test_attach_and_status_never_create_resources(session_runtime) -> None:
    calls: list[str] = []
    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=lambda **_values: {
            "state": "stopped",
            "running": False,
            "owned": False,
        },
        start=lambda **_values: calls.append("start"),
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=lambda **_values: {"running": False, "owned": False, "windows": []},
        start=lambda **_values: calls.append("start"),
    )
    assert session_runtime.status()["state"] == "stopped"
    with pytest.raises(RuntimeError, match="not healthy"):
        session_runtime.attach()
    assert calls == []


def test_uncertain_roba_probe_blocks_start_stop_and_reset_before_mutation(
    session_runtime,
) -> None:
    calls: list[str] = []
    session_runtime.runtime = FakeApi(
        paths=lambda **_values: _paths(),
        status=lambda **_values: {"state": "uncertain", "running": False, "owned": False},
        start=lambda **_values: calls.append("roba-start"),
        stop=lambda **_values: calls.append("roba-stop"),
    )
    session_runtime.tmux = FakeApi(
        socket_path=lambda _root: Path("/tmp/cockpit/tmux.sock"),
        config_path=lambda: Path("/tmp/cockpit/tmux.conf"),
        status=lambda **_values: {
            "server_running": False,
            "server_owned": False,
            "running": False,
            "owned": False,
            "windows": [],
        },
        start=lambda **_values: calls.append("tmux-start"),
        stop=lambda **_values: calls.append("tmux-stop"),
    )

    assert session_runtime.status()["state"] == "uncertain"
    with pytest.raises(RuntimeError, match="uncertain"):
        session_runtime.start(shell_command=["shell"], status_command=["status"], attach=False)
    with pytest.raises(RuntimeError, match="unowned ROBA"):
        session_runtime.stop()
    with pytest.raises(RuntimeError, match="unowned ROBA"):
        session_runtime.reset(shell_command=["shell"], status_command=["status"], attach=False)
    assert calls == []
