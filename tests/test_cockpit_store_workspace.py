from __future__ import annotations

import fcntl
import os
import pty
import struct
import subprocess
import sys
import termios
import time
from threading import Thread

import pytest


def tmux(socket, *args):
    result = subprocess.run(["tmux", "-S", str(socket), *args], text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def wait_for(check):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        if check():
            return
        time.sleep(0.05)
    raise AssertionError("timed out waiting for real tmux state")



def drain_terminal(fd):
    def drain():
        try:
            while os.read(fd, 65536):
                pass
        except OSError:
            pass
    Thread(target=drain, daemon=True).start()


def test_real_store_window_roles_reuse_exit_respawn_detach_and_session_isolation(
    store_graph, monkeypatch,
):
    create, runtime, _ = store_graph
    workspace = create("skaldos/cockpit/cockpit_session").api
    monkeypatch.setenv("TMUX", "/not/the/host/socket,1,0")
    start = workspace.require("start_master")(
        session="a", shell_command=["sleep", "300"], status_command=["sleep", "300"],
        workbench_command=["sleep", "300"], attach=False)
    sock = start["tmux"]["socket"]
    commands = {"A": ["sleep", "300"], "B": ["sh", "-c", "echo local-test-exit; exit 7"]}
    first = workspace.require("open_stores")(session="a", commands=commands)
    a, b = (first["panes"][side]["pane_id"] for side in ("A", "B"))
    wait_for(lambda: tmux(sock, "display-message", "-p", "-t", b, "#{pane_dead}") == "1")
    assert "status 7" in tmux(sock, "capture-pane", "-p", "-t", b)
    apid = tmux(sock, "display-message", "-p", "-t", a, "#{pane_pid}")
    commands["B"] = ["sleep", "300"]
    again = workspace.require("open_stores")(session="a", commands=commands)
    assert again["panes"]["A"] == {"pane_id": a, "action": "focused"}
    assert again["panes"]["B"] == {"pane_id": b, "action": "respawned"}
    assert tmux(sock, "display-message", "-p", "-t", a, "#{pane_pid}") == apid
    assert len(tmux(sock, "list-panes", "-t", "a:stores").splitlines()) == 2
    assert tmux(sock, "list-windows", "-t", "a", "-F", "#{window_name}").splitlines() == [
        "control", "stores"]
    assert set(tmux(sock, "list-panes", "-t", "a:stores", "-F",
                    "#{@cockpit-pane-role}").splitlines()) == {
        "skaldos.dix-cockpit.stores-a.v1", "skaldos.dix-cockpit.stores-b.v1"}
    secret = runtime.require("owner_environment")(session="a")["ROBA_CONTROL_TOKEN"]
    for args in (("show-environment", "-t", "a"),
                 ("show-options", "-t", "a"),
                 ("list-panes", "-t", "a:stores", "-F", "#{pane_title} #{pane_start_command}")):
        assert secret not in tmux(sock, *args)
    # Real PTY attach -> explicit detach -> reattach, no lifecycle mutation.
    monkeypatch.delenv("TMUX")
    for _ in range(2):
        main, child = pty.openpty()
        fcntl.ioctl(child, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 140, 0, 0))
        process = subprocess.Popen(["tmux", "-S", sock, "attach-session", "-t", "a"],
                                   stdin=child, stdout=child, stderr=child,
                                   env={**os.environ, "TERM": "xterm-256color"})
        os.close(child)
        drain_terminal(main)
        try:
            wait_for(lambda: bool(tmux(sock, "list-clients", "-F", "#{client_name}")))
            tmux(sock, "detach-client", "-s", "a")
            assert process.wait(timeout=5) == 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            os.close(main)
    assert workspace.require("status")(session="a")["running"] is True
    workspace.require("start")(session="b", shell_command=["sleep", "300"],
                               status_command=["sleep", "300"], attach=False)
    other = workspace.require("open_stores")(session="b", commands=commands)
    assert other["panes"]["A"]["pane_id"] != a
    workspace.require("stop")(session="a")
    assert workspace.require("status")(session="b")["running"] is True
    workspace.require("reset")(session="b", shell_command=["sleep", "300"],
                               status_command=["sleep", "300"], attach=False)
    assert workspace.require("status")(session="b")["tmux"]["windows"] == ["control"]
    workspace.require("stop")(session="b")


def test_store_window_and_pane_drift_fail_closed(store_graph):
    create, _, _ = store_graph
    workspace = create("skaldos/cockpit/cockpit_session").api
    result = workspace.require("start")(session="a", shell_command=["sleep", "300"],
                                        status_command=["sleep", "300"], attach=False)
    sock = result["tmux"]["socket"]
    tmux(sock, "new-window", "-d", "-t", "a", "-n", "stores", "sleep 300")
    before = tmux(sock, "list-panes", "-t", "a:stores", "-F", "#{pane_id} #{pane_pid}")
    with pytest.raises(RuntimeError, match="foreign"):
        workspace.require("open_stores")(session="a", commands={"A": ["true"], "B": ["true"]})
    assert tmux(sock, "list-panes", "-t", "a:stores", "-F", "#{pane_id} #{pane_pid}") == before
    tmux(sock, "kill-window", "-t", "a:stores")
    result = workspace.require("open_stores")(
        session="a", commands={"A": ["sleep", "300"], "B": ["sleep", "300"]})
    pane = result["panes"]["B"]["pane_id"]
    tmux(sock, "set-option", "-p", "-t", pane, "@cockpit-pane-role", "foreign")
    before = tmux(sock, "list-panes", "-t", "a:stores", "-F", "#{pane_id} #{pane_pid}")
    with pytest.raises(RuntimeError, match="foreign"):
        workspace.require("open_stores")(session="a", commands={"A": ["true"], "B": ["true"]})
    assert tmux(sock, "list-panes", "-t", "a:stores", "-F", "#{pane_id} #{pane_pid}") == before
    workspace.require("stop")(session="a")


def test_installed_master_opens_two_real_visidata_browsers_from_command(
    store_graph, tmp_path, monkeypatch,
):
    from pathlib import Path

    from test_cockpit_roba_store import external

    root = Path(__file__).parents[1]
    dix = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
    python = Path(os.environ.get("DIX_PYTHON", sys.executable))
    monkeypatch.setenv("PYTHONPATH", str(dix / "src"))
    create, runtime, owner, conn, _, _, _ = external(store_graph)
    venv, launchers, binary, tools = (tmp_path / x for x in ("v", "l", "b", "t"))
    (venv / "bin").mkdir(parents=True)
    tools.mkdir()
    (tools / "uv").write_text("#!/bin/sh\nexit 0\n")
    (tools / "uv").chmod(0o755)
    (venv / "bin/python").write_text(f'#!/bin/sh\nexec "{python}" "$@"\n')
    (venv / "bin/python").chmod(0o755)
    env_file = tmp_path / "env"
    env_file.write_text("\n".join(f'export {key}="{val}"' for key, val in {
        "DIX_SOURCE_ROOT": dix, "DIX_VENV": venv, "DIX_LAUNCHERS": launchers,
        "DIX_BIN": binary, "DIX_ENV": env_file,
    }.items()) + "\n")
    monkeypatch.setenv("DIX_ENV", str(env_file))
    monkeypatch.setenv("DIX_BIN", str(binary))
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    for installer in ("install", "install-ui"):
        result = subprocess.run([str(root / "cockpit/integrations" / installer)],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    browser = create("skaldos/cockpit/store_browser")
    browser.runtime.catalog.require("create")(
        {"store_id": "external", "provider": "roba", "connection": conn}, "a")
    before = owner.snapshot()
    workspace = create("skaldos/cockpit/cockpit_session").api
    started = workspace.require("start_master")(
        session="a", shell_command=["sleep", "300"], status_command=["sleep", "300"],
        workbench_command=[str(binary / "dix-cockpit-master-workbench"), "--session", "a"],
        store_command=[str(binary / "dix-cockpit-store-workbench"), "--session", "a"],
        attach=False)
    sock, master = started["tmux"]["socket"], started["workbench"]["pane_id"]
    # Attach a real client: VisiData needs a practical screen size, not tmux's tiny default.
    main, child = pty.openpty()
    fcntl.ioctl(child, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 150, 0, 0))
    client = subprocess.Popen(["tmux", "-S", sock, "attach-session", "-t", "a"],
                              stdin=child, stdout=child, stderr=child,
                              env={**os.environ, "TERM": "xterm-256color"})
    os.close(child)
    drain_terminal(main)
    try:
        wait_for(lambda: "Press Enter" in tmux(sock, "capture-pane", "-p", "-t", master))
        tmux(sock, "send-keys", "-t", master, "Enter")
        try:
            wait_for(lambda: "connection" in tmux(sock, "capture-pane", "-p", "-t", master))
        except AssertionError:
            screen = tmux(sock, "capture-pane", "-p", "-S", "-", "-t", master)
            screen = screen.replace(conn["token"], "[redacted]").replace(
                runtime.require("owner_environment")(session="a")["ROBA_CONTROL_TOKEN"],
                "[redacted]")
            raise AssertionError("Master did not start: " + screen) from None
        store = started["store"]["pane_id"]
        wait_for(lambda: "external" in tmux(sock, "capture-pane", "-p", "-t", store))
        tmux(sock, "send-keys", "-t", store, "Enter")
        try:
            wait_for(lambda: "store_id" in tmux(sock, "capture-pane", "-p", "-t", store))
        except AssertionError:
            screen = tmux(sock, "capture-pane", "-p", "-S", "-", "-t", store)
            for secret in (conn["token"], runtime.require("owner_environment")(
                    session="a")["ROBA_CONTROL_TOKEN"]):
                screen = screen.replace(secret, "[redacted]")
            raise AssertionError("Store did not open: " + screen) from None
        tmux(sock, "send-keys", "-t", store, "q")
        wait_for(lambda: "store_id" not in tmux(sock, "capture-pane", "-p", "-t", store))
        wait_for(lambda: "roba" in tmux(sock, "capture-pane", "-p", "-t", store))
        tmux(sock, "send-keys", "-t", store, "q")
        assert tmux(sock, "display-message", "-p", "-t", store, "#{pane_dead}") == "0"
        tmux(sock, "send-keys", "-t", store, "g", "q")
        wait_for(lambda: tmux(sock, "display-message", "-p", "-t", store, "#{pane_dead}") == "1")
        restored = workspace.require("start_master")(
            session="a", shell_command=["sleep", "300"], status_command=["sleep", "300"],
            workbench_command=[str(binary / "dix-cockpit-master-workbench"), "--session", "a"],
            store_command=[str(binary / "dix-cockpit-store-workbench"), "--session", "a"],
            attach=False)
        assert restored["store"] == {"pane_id": store, "action": "respawned"}
        wait_for(lambda: "external" in tmux(sock, "capture-pane", "-p", "-t", store))
        assert len(tmux(sock, "list-panes", "-t", "a:control").splitlines()) == 4
        tmux(sock, "send-keys", "-t", master, "z", "S")
        wait_for(lambda: "stores" in tmux(sock, "list-windows", "-t", "a", "-F", "#{window_name}"))
        wait_for(lambda: len(tmux(sock, "list-panes", "-t", "a:stores",
                                   "-F", "#{pane_id}").splitlines()) == 2)
        panes = tmux(sock, "list-panes", "-t", "a:stores", "-F", "#{pane_id}").splitlines()
        assert len(panes) == 2
        for pane in panes:
            wait_for(lambda pane=pane: "external" in tmux(sock, "capture-pane", "-p", "-t", pane))
            tmux(sock, "send-keys", "-t", pane, "Enter")
            wait_for(lambda pane=pane: "settings" in tmux(sock, "capture-pane", "-p", "-t", pane))
        # Exercise the actual terminal bindings, not only the controller methods.
        tmux(sock, "send-keys", "-t", panes[0], "z", "B")
        wait_for(lambda: "settings" not in tmux(sock, "capture-pane", "-p", "-t", panes[0]))
        assert "settings" in tmux(sock, "capture-pane", "-p", "-t", panes[1])
        tmux(sock, "send-keys", "-t", panes[1], "z", "U")
        wait_for(lambda: "settings" not in tmux(sock, "capture-pane", "-p", "-t", panes[1]))
        assert owner.snapshot() == before
        # No capability is ever put in tmux environment, argv, titles or error/status output.
        owner_secret = runtime.require("owner_environment")(session="a")["ROBA_CONTROL_TOKEN"]
        for pane in panes + [master]:
            screen = tmux(sock, "capture-pane", "-p", "-t", pane)
            assert "Traceback" not in screen and "error:" not in screen.lower()
            assert owner_secret not in screen and conn["token"] not in screen
        for log in (store_graph[2] / "s").rglob("*"):
            if log.is_file():
                content = log.read_bytes()
                assert owner_secret.encode() not in content and conn["token"].encode() not in content
        metadata = tmux(sock, "list-panes", "-a", "-F",
                        "#{pane_pid} #{pane_title} #{pane_start_command}")
        assert owner_secret not in metadata and conn["token"] not in metadata
        tmux(sock, "detach-client", "-s", "a")
        assert client.wait(timeout=5) == 0
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(timeout=5)
        os.close(main)
        workspace.require("stop")(session="a")


def test_ui_stores_builds_only_session_logo_and_side_args(load_runtime, api, monkeypatch):
    runtime = load_runtime("cockpit/apps/ui/runtime.py")
    events = []
    ui = runtime(context=None, config={}, session=api(
        open_stores=lambda **kw: events.append(kw),
        attach=lambda **kw: events.append("attached")))
    monkeypatch.setenv("DIX_BIN", "/test/bin")
    monkeypatch.setenv("TMUX", "current")
    assert ui.main(["stores", "--session", "mine", "--logo", "roba"]) == 0
    assert events == [{"session": "mine", "commands": {
        side: ["/test/bin/dix-cockpit-store-browser", "--session", "mine", "--logo", "roba",
               "--side", side] for side in ("A", "B")}}]
    monkeypatch.delenv("TMUX")
    assert ui.main(["stores"]) == 0
    assert events[-1] == "attached"
