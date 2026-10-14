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
