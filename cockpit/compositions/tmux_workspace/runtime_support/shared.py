from __future__ import annotations

import os
import re
import shlex
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

_SESSION = re.compile(r"[A-Za-z0-9_.-]+\Z")
_WINDOW = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SOCKET_LIMIT = 107
_SERVER_OWNER_OPTION = "@cockpit-server-owner"
_SERVER_OWNER_MARKER = "skaldos.dix-cockpit.tmux-server.v1"
_SESSION_OWNER_OPTION = "@cockpit-owner"
_SESSION_OWNER_MARKER = "skaldos.dix-cockpit.tmux-session.v1"
_PANE_ROLE_OPTION = "@cockpit-pane-role"
_STATUS_ROLE = "skaldos.dix-cockpit.runtime-status.v1"
_SHELL_ROLE = "skaldos.dix-cockpit.owner-shell.v1"
_MASTER_ROLE = "skaldos.dix-cockpit.master-workbench.v1"
_STORE_ROLE = "skaldos.dix-cockpit.store-workbench.v1"
_SELECTED_WINDOW_ROLE = "skaldos.dix-cockpit.store-window.v1"
_SELECTED_ROLES = {"status": "skaldos.dix-cockpit.store-status.v1",
                   "browser": "skaldos.dix-cockpit.selected-browser.v1"}
_STORES_WINDOW_ROLE = "skaldos.dix-cockpit.stores.v1"
_STORES_ROLES = {"A": "skaldos.dix-cockpit.stores-a.v1",
                 "B": "skaldos.dix-cockpit.stores-b.v1"}


class TmuxWorkspaceError(RuntimeError):
    """The isolated Cockpit tmux workspace could not satisfy one operation."""



class TmuxTransport:
    """The composition's command transport and unchanged low-level checks."""

    def __init__(self, config: Mapping[str, object]) -> None:
        self.config = config

    def _socket(self, value: str | Path) -> Path:
        path = Path(value).expanduser().resolve(strict=False)
        if len(os.fsencode(path)) > _SOCKET_LIMIT:
            raise TmuxWorkspaceError(
                f"Cockpit tmux socket exceeds platform limit ({len(os.fsencode(path))} > "
                f"{_SOCKET_LIMIT}): {path}"
            )
        return path


    def _base(self, socket: Path) -> tuple[str, ...]:
        binary = self.config.get("tmux_binary", "tmux")
        if not isinstance(binary, str) or not binary.strip():
            raise TypeError("tmux_binary must be a non-empty string")
        return binary, "-S", str(socket)


    @staticmethod
    def _public_status(
        *,
        session: str,
        socket: Path,
        server_running: bool,
        server_owned: bool,
        running: bool,
        session_owned: bool,
        windows: list[str],
    ) -> dict[str, object]:
        return {
            "session": session,
            "socket": str(socket),
            "server_running": server_running,
            "server_owned": server_owned,
            "running": running,
            "session_owned": session_owned,
            "owned": server_owned and session_owned,
            "windows": windows,
        }


    @staticmethod
    def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key != "TMUX" and not _secret_key(key)
        }
        return subprocess.run(
            list(command),
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )


    @staticmethod
    def _require(result: subprocess.CompletedProcess[str], operation: str) -> None:
        if result.returncode:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown tmux error"
            raise TmuxWorkspaceError(f"{operation} failed: {detail}")



def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or not _SESSION.fullmatch(value):
        raise ValueError(f"Cockpit {label} must match {_SESSION.pattern}")
    return value


def _shell_command(value: Sequence[str]) -> str:
    if isinstance(value, (str, bytes, bytearray)) or not value:
        raise TypeError("Cockpit child command must be a non-empty argument sequence")
    arguments = list(value)
    if not all(isinstance(item, str) and item for item in arguments):
        raise TypeError("Cockpit child command arguments must be non-empty strings")
    return shlex.join(arguments)


def _string_environment(value: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) and key and isinstance(item, str) for key, item in value.items()
    ):
        raise TypeError("Cockpit tmux environment must be a string mapping")
    secret = next((key for key in value if _secret_key(key)), None)
    if secret is not None:
        raise ValueError(f"Cockpit tmux environment must not contain secret key: {secret}")
    return dict(value)


def _secret_key(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except FileNotFoundError:
        return False


def _server_absent(result: subprocess.CompletedProcess[str], socket: Path) -> bool:
    if not socket.exists() and not socket.is_symlink():
        return True
    detail = (result.stderr + "\n" + result.stdout).lower()
    return any(
        marker in detail
        for marker in (
            "no server running",
            "no such file or directory",
            "connection refused",
        )
    )
