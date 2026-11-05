from __future__ import annotations

import os
import subprocess
import time
from threading import Thread


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

