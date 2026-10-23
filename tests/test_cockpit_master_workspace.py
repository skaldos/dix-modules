from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from dix.core import (
    ApplicationComponent,
    CompositionComponent,
    ModuleComponent,
    create_core_component_registry,
)
from dix.core.application import ApplicationInstanceSpec
from dix.core.composition import CompositionInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class FakeApi:
    def __init__(self, **functions: Callable[..., object]) -> None:
        self.functions = functions

    def require(self, function_id: str) -> Callable[..., object]:
        return self.functions[function_id]


def _registry():
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    loaded: list[str] = []
    for module_id in ("dix/state", "dix/cli", "dix/norn", "dix/roba"):
        modules.load_module(first_party_module_path(module_id), module_id=module_id)
        loaded.append(module_id)
    modules.load_module(ROOT / "visidata", module_id="skaldos/visidata")
    loaded.append("skaldos/visidata")
    modules.load_module(ROOT / "cockpit", module_id="skaldos/cockpit")
    loaded.append("skaldos/cockpit")
    return registry, modules, loaded


def test_ui_builds_only_non_secret_helper_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    registry, modules, loaded = _registry()
    apps = registry.require("application", ApplicationComponent)
    app = apps.create_instance(
        ApplicationInstanceSpec("ui", "skaldos/cockpit/ui", {}, tmp_path),
        owner_scope_id="cockpit-ui-test",
    )
    try:
        calls: list[dict[str, object]] = []
        app.runtime.session = FakeApi(
            start_master=lambda **values: calls.append(values) or {"running": True}
        )
        monkeypatch.setenv("DIX_BIN", "/opt/dix/bin")
        assert app.api.require("main")(["start", "--session", "private", "--logo", "roba"]) == 0
        assert len(calls) == 1
        values = calls[0]
        assert values["attach"] is True
        assert values["workbench_command"] == [
            "/opt/dix/bin/dix-cockpit-master-workbench",
            "--session",
            "private",
            "--logo",
            "roba",
        ]
        assert "token" not in repr(values).lower()
        assert app.api.require("main")(["--help"]) == 0
        assert "start" in capsys.readouterr().out
    finally:
        apps.destroy_instance("cockpit-ui-test", "ui")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_session_master_orders_start_open_attach_and_rolls_back_only_fresh_resources(
    tmp_path: Path,
) -> None:
    registry, modules, loaded = _registry()
    compositions = registry.require("composition", CompositionComponent)
    instance = compositions.create_instance(
        CompositionInstanceSpec(
            "session", "skaldos/cockpit/cockpit_session", {}, tmp_path
        ),
        owner_scope_id="cockpit-master-session-test",
    )
    runtime = instance.runtime
    events: list[str] = []
    try:
        runtime.start = lambda **_values: {
            "running": True,
            "created": {"roba": False, "tmux": False},
            "attached": False,
        }
        runtime.open_master_workbench = (
            lambda **_values: events.append("open")
            or {"session": "dix", "pane_id": "%3", "action": "created"}
        )
        runtime.attach = lambda **_values: events.append("attach") or 0
        result = runtime.start_master(
            shell_command=["shell"],
            status_command=["status"],
            workbench_command=["workbench"],
        )
        assert events == ["open", "attach"]
        assert result["workbench"]["pane_id"] == "%3"
        assert result["attached"] is True

        runtime.start = lambda **_values: {
            "running": True,
            "created": {"roba": True, "tmux": True},
            "attached": False,
        }
        runtime.open_master_workbench = lambda **_values: (_ for _ in ()).throw(
            RuntimeError("pane failed")
        )
        runtime.paths = lambda **_values: {"socket": "/tmp/cockpit/tmux.sock"}
        runtime.tmux = FakeApi(stop=lambda **_values: events.append("tmux-stop") or True)
        runtime.runtime = FakeApi(
            stop=lambda **_values: events.append("roba-stop") or {"stopped": True}
        )
        with pytest.raises(RuntimeError, match="pane failed"):
            runtime.start_master(
                shell_command=["shell"],
                status_command=["status"],
                workbench_command=["workbench"],
                attach=False,
            )
        assert events[-2:] == ["tmux-stop", "roba-stop"]
    finally:
        compositions.destroy_instance("cockpit-master-session-test", "session")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)


def test_four_master_roles_geometry_reuse_respawn_foreign_and_cleanup(store_graph):
    from test_cockpit_store_workspace import tmux, wait_for

    create, runtime, root = store_graph
    workspace = create('skaldos/cockpit/cockpit_session').api
    args = {'session': 'a', 'shell_command': ['sleep', '300'], 'status_command': ['sleep', '300'],
            'workbench_command': ['sleep', '300'], 'store_command': ['sleep', '300'], 'attach': False}
    result = workspace.require('start_master')(**args)
    sock = result['tmux']['socket']

    def panes():
        rows = tmux(sock, 'list-panes', '-t', 'a:control', '-F',
                    '#{pane_id}|#{@cockpit-pane-role}|#{pane_pid}|#{pane_left}|#{pane_top}').splitlines()
        return {r.split('|')[1].split('.')[-2]: r.split('|') for r in rows}

    first = panes()
    assert set(first) == {'runtime-status', 'owner-shell', 'master-workbench', 'store-workbench'}
    assert int(first['runtime-status'][3]) == int(first['store-workbench'][3]) == 0
    assert int(first['master-workbench'][3]) == int(first['owner-shell'][3]) > 0
    assert int(first['runtime-status'][4]) == int(first['master-workbench'][4])
    assert int(first['store-workbench'][4]) == int(first['owner-shell'][4]) > 0
    result = workspace.require('start_master')(**args)
    assert result['store']['action'] == result['workbench']['action'] == 'focused'
    assert panes() == first
    for key in ('store-workbench', 'master-workbench'):
        ident = first[key][0]
        tmux(sock, 'respawn-pane', '-k', '-t', ident, 'exit 7')
        wait_for(lambda ident=ident: tmux(sock, 'display-message', '-p', '-t', ident, '#{pane_dead}') == '1')
        result = workspace.require('start_master')(**args)
        assert result['store' if key == 'store-workbench' else 'workbench']['action'] == 'respawned'
        assert panes()[key][0] == ident
    # Missing own role is completed without replacing the other processes.
    before = panes()
    tmux(sock, 'kill-pane', '-t', before['store-workbench'][0])
    result = workspace.require('start_master')(**args)
    assert result['store']['action'] == 'created'
    assert panes()['master-workbench'][2] == before['master-workbench'][2]
    # Unknown pane/role and duplicate roles fail before pane changes.
    store = result['store']['pane_id']
    for bad_role in ('foreign', 'skaldos.dix-cockpit.owner-shell.v1'):
        tmux(sock, 'set-option', '-p', '-t', store, '@cockpit-pane-role', bad_role)
        before = tmux(sock, 'list-panes', '-t', 'a:control', '-F', '#{pane_id} #{pane_pid}')
        with pytest.raises(RuntimeError, match='foreign|ambiguous'):
            workspace.require('start_master')(**args)
        assert tmux(sock, 'list-panes', '-t', 'a:control', '-F', '#{pane_id} #{pane_pid}') == before
    tmux(sock, 'set-option', '-p', '-t', store, '@cockpit-pane-role',
         'skaldos.dix-cockpit.store-workbench.v1')
    other = workspace.require('start_master')(**{**args, 'session': 'b'})
    assert other['store']['pane_id'] != store
    secret = runtime.require('owner_environment')(session='a')['ROBA_CONTROL_TOKEN']
    metadata = tmux(sock, 'list-panes', '-a', '-F',
                    '#{pane_title} #{pane_start_command} #{@cockpit-pane-role}')
    assert secret not in metadata
    workspace.require('stop')(session='a')
    assert workspace.require('status')(session='b')['running']
    workspace.require('reset')(session='b', shell_command=['sleep', '300'],
                               status_command=['sleep', '300'], attach=False)
    assert len(tmux(sock, 'list-panes', '-t', 'b:control').splitlines()) == 2
    workspace.require('stop')(session='b')
    assert not (root / 'r/tmux.sock').exists()
