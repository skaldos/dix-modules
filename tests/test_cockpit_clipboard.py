from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
COPY = ROOT / "cockpit/integrations/bin/dix-cockpit-clipboard-copy"
PASTE = ROOT / "cockpit/integrations/bin/dix-cockpit-clipboard-paste"


def _tool(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n")
    path.chmod(0o755)
    return path


def _run(path: Path, environment: dict[str, str], data: bytes = b""):
    return subprocess.run(
        [str(path)],
        input=data,
        env=environment,
        capture_output=True,
        check=False,
    )


def test_wayland_copy_and_paste_win_without_shell_interpolation(tmp_path: Path) -> None:
    tools = tmp_path / "bin"
    tools.mkdir()
    copied = tmp_path / "copied"
    source = tmp_path / "source"
    source.write_bytes(b"wayland\x00payload")
    _tool(tools, "wl-copy", f'cat > "{copied}"')
    _tool(tools, "wl-paste", f'cat "{source}"')
    _tool(tools, "xclip", "exit 91")
    environment = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "WAYLAND_DISPLAY": "wayland-1",
        "DISPLAY": ":1",
    }
    payload = b"$HOME;$(touch nope)\nsecond line\x00"
    copy = _run(COPY, environment, payload)
    paste = _run(PASTE, environment)
    assert copy.returncode == 0 and copied.read_bytes() == payload
    assert paste.returncode == 0 and paste.stdout == source.read_bytes()


def test_xclip_is_second_adapter(tmp_path: Path) -> None:
    tools = tmp_path / "bin"
    tools.mkdir()
    copied = tmp_path / "copied"
    source = tmp_path / "source"
    source.write_bytes(b"xclip payload")
    _tool(
        tools,
        "xclip",
        f'if [ "$3" = "-in" ]; then cat > "{copied}"; else cat "{source}"; fi',
    )
    environment = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "DISPLAY": ":1",
        "WAYLAND_DISPLAY": "",
    }
    assert _run(COPY, environment, b"copy x").returncode == 0
    paste = _run(PASTE, environment)
    assert copied.read_bytes() == b"copy x"
    assert paste.stdout == b"xclip payload"


def test_tmux_buffer_fallback_uses_explicit_cockpit_socket(tmp_path: Path) -> None:
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "tmux.log"
    buffer = tmp_path / "buffer"
    _tool(
        tools,
        "fake-tmux",
        f'''printf '%s\\n' "$*" >> "{log}"
case "$*" in
  *"load-buffer -"*) cat > "{buffer}" ;;
  *"save-buffer -"*) cat "{buffer}" ;;
esac''',
    )
    socket = tmp_path / "cockpit.sock"
    environment = {
        **os.environ,
        "PATH": f"{tools}:/usr/bin:/bin",
        "WAYLAND_DISPLAY": "",
        "DISPLAY": "",
        "DIX_COCKPIT_TMUX_BIN": "fake-tmux",
        "DIX_COCKPIT_TMUX_SOCKET": str(socket),
    }
    payload = b"tmux $payload; untouched\n"
    copy = _run(COPY, environment, payload)
    paste = _run(PASTE, environment)
    assert copy.returncode == paste.returncode == 0
    assert buffer.read_bytes() == payload
    assert paste.stdout == payload
    commands = log.read_text().splitlines()
    assert commands[0] == f"-S {socket} load-buffer -"
    assert commands[-1] == f"-S {socket} save-buffer -"
    assert "System clipboard unavailable" in copy.stderr.decode()
    assert "System clipboard unavailable" in paste.stderr.decode()


def test_real_prefix_paste_keeps_original_pane_during_delayed_adapter(store_graph, tmp_path):
    import fcntl
    import pty
    import shlex
    import struct
    import termios

    from test_cockpit_store_workspace import drain_terminal, tmux, wait_for

    create, _, root = store_graph
    workspace = create("skaldos/cockpit/cockpit_session").api
    result = workspace.require("start_master")(
        session="a", shell_command=["sleep", "300"], status_command=["sleep", "300"],
        workbench_command=["sleep", "300"], attach=False)
    sock = result["tmux"]["socket"]
    begun, release = root / "begun", root / "release"
    adapter = _tool(tmp_path, "delayed-paste", f'''
: > {shlex.quote(str(begun))}
while [ ! -e {shlex.quote(str(release))} ]; do sleep .03; done
printf 'literal-paste-payload\\n'
''')
    tmux(sock, "set-environment", "-t", "a", "DIX_COCKPIT_CLIPBOARD_PASTE", str(adapter))
    targets = []
    for name in ("source", "other"):
        output = root / name
        command = f"IFS= read -r value; printf '%s' \"$value\" > {shlex.quote(str(output))}; sleep 300"
        pane = tmux(sock, "new-window", "-t", "a", "-P", "-F", "#{pane_id}",
                    "sh -c " + shlex.quote(command))
        targets.append((pane, output))
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 150, 0, 0))
    client = subprocess.Popen(["tmux", "-S", sock, "attach-session", "-t", "a"],
                              stdin=slave, stdout=slave, stderr=slave,
                              env={**os.environ, "TERM": "xterm-256color", "TMUX": ""})
    os.close(slave)
    drain_terminal(master)
    try:
        wait_for(lambda: bool(tmux(sock, "list-clients", "-F", "#{client_name}")))
        pane, output = targets[0]
        tmux(sock, "select-window", "-t", pane)
        tmux(sock, "select-pane", "-t", pane)
        # Real client input, not a direct paste-buffer invocation.
        os.write(master, b"\x01")
        wait_for(lambda: tmux(sock, "list-clients", "-F", "#{client_prefix}") == "1")
        os.write(master, b"p")
        try:
            wait_for(begun.exists)
        except AssertionError:
            raise AssertionError(tmux(sock, "list-keys", "-T", "prefix", "p") + " / " +
                                 tmux(sock, "capture-pane", "-p", "-t", pane)) from None
        tmux(sock, "select-window", "-t", targets[1][0])
        tmux(sock, "select-pane", "-t", targets[1][0])
        release.touch()
        wait_for(output.exists)
        assert output.read_text() == "literal-paste-payload"
        assert not targets[1][1].exists()
    finally:
        release.touch()
        tmux(sock, "detach-client", "-s", "a")
        client.wait(timeout=5)
        os.close(master)
        workspace.require("stop")(session="a")
