"""Byte-buffered clipboard adapter; no payload in argv, diagnostics or on disk."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def run(command, payload=None):
    try:
        return subprocess.run(command, input=payload, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return None


def main(mode):
    copying = mode == "copy"
    payload = sys.stdin.buffer.read() if copying else None
    command = None
    wayland = "wl-copy" if copying else "wl-paste"
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which(wayland):
        command = [wayland] + ([] if copying else ["--no-newline"])
    elif os.environ.get("DISPLAY") and shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard", "-in" if copying else "-out"]
    if command:
        result = run(command, payload)
        if result is not None and result.returncode == 0:
            if not copying:
                sys.stdout.buffer.write(result.stdout)
            return 0
    # A failed adapter's partial stdout is intentionally discarded before fallback.
    socket = os.environ.get("DIX_COCKPIT_TMUX_SOCKET")
    if not socket:
        print("Private Cockpit tmux socket is required for clipboard fallback", file=sys.stderr)
        return 1
    # tmux load-buffer silently ignores zero bytes and would retain an older clipboard.
    # Do not invent destructive clear/history semantics or report that as a successful copy.
    if copying and not payload:
        print("Cockpit tmux buffer cannot store an empty payload; clipboard unchanged", file=sys.stderr)
        return 1
    tmux = [os.environ.get("DIX_COCKPIT_TMUX_BIN", "tmux"), "-S", socket]
    result = run([*tmux, "load-buffer" if copying else "save-buffer", "-"], payload)
    if result is None or result.returncode:
        print("Cockpit clipboard fallback failed", file=sys.stderr)
        return 1
    message = "System clipboard unavailable; " + (
        "copied to Cockpit tmux buffer" if copying else "pasting Cockpit tmux buffer")
    run([*tmux, "display-message", message])
    print(message, file=sys.stderr)
    if not copying:
        sys.stdout.buffer.write(result.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
