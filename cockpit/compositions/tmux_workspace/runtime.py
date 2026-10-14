from __future__ import annotations

import hashlib
import os
import re
import shlex
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext

_SESSION = re.compile(r"[A-Za-z0-9_.-]+\Z")
_WINDOW = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SOCKET_LIMIT = 107


class TmuxWorkspaceError(RuntimeError):
    """The isolated Cockpit tmux workspace could not satisfy one operation."""


class Runtime:
    """Own command plans for exactly one isolated tmux server socket."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def socket_path(self, runtime_root: str | Path) -> Path:
        path = Path(runtime_root).expanduser().resolve(strict=False) / "tmux.sock"
        encoded = os.fsencode(path)
        if len(encoded) > _SOCKET_LIMIT:
            raise TmuxWorkspaceError(
                f"Cockpit tmux socket exceeds platform limit ({len(encoded)} > {_SOCKET_LIMIT}): "
                f"{path}"
            )
        return path

    def config_path(self) -> Path:
        configured = self.config.get("tmux_config")
        if configured is None:
            configured = os.environ.get("DIX_COCKPIT_TMUX_CONFIG")
        if configured is not None:
            if not isinstance(configured, str) or not configured.strip():
                raise TypeError("tmux_config must be a non-empty path string")
            return Path(configured).expanduser().resolve(strict=False)
        return Path(__file__).parents[2] / "integrations" / "tmux" / "cockpit.conf"

    def status(self, *, session: str, socket: str | Path) -> dict[str, object]:
        session = _name(session, "session")
        socket_path = self._socket(socket)
        result = self._run((*self._base(socket_path), "has-session", "-t", f"={session}"))
        if result.returncode == 0:
            windows = self._run(
                (
                    *self._base(socket_path),
                    "list-windows",
                    "-t",
                    f"={session}",
                    "-F",
                    "#{window_name}",
                )
            )
            self._require(windows, "list Cockpit windows")
            return {
                "session": session,
                "socket": str(socket_path),
                "running": True,
                "windows": [line for line in windows.stdout.splitlines() if line],
            }
        return {"session": session, "socket": str(socket_path), "running": False, "windows": []}

    def start(
        self,
        *,
        session: str,
        socket: str | Path,
        control_command: Sequence[str],
        environment: Mapping[str, str],
        attach: bool = True,
    ) -> dict[str, object]:
        session = _name(session, "session")
        socket_path = self._socket(socket)
        command = _shell_command(control_command)
        env = _string_environment(environment)
        current = self.status(session=session, socket=socket_path)
        created = False
        if current["running"] is True:
            self._require(
                self._run(
                    (*self._base(socket_path), "select-window", "-t", f"={session}:control")
                ),
                "focus Cockpit control window",
            )
        else:
            socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            socket_path.parent.chmod(0o700)
            start = [*self._base(socket_path)]
            if not socket_path.exists():
                config = self.config_path()
                if not config.is_file():
                    raise TmuxWorkspaceError(f"Cockpit tmux config does not exist: {config}")
                start.extend(("-f", str(config)))
            start.extend(("new-session", "-d", "-s", session, "-n", "control"))
            for key, value in env.items():
                start.extend(("-e", f"{key}={value}"))
            start.append(command)
            result = self._run(tuple(start))
            if result.returncode != 0 and socket_path.exists() and _is_socket(socket_path):
                probe = self._run((*self._base(socket_path), "list-sessions"))
                if probe.returncode != 0 and "no server" in probe.stderr.lower():
                    socket_path.unlink(missing_ok=True)
                    result = self._run(tuple(start[:3] + ["-f", str(self.config_path())] + start[3:]))
            self._require(result, "start Cockpit session")
            created = True
        if attach:
            self._require(
                self._run((*self._base(socket_path), "attach-session", "-t", f"={session}")),
                "attach Cockpit session",
            )
        result = self.status(session=session, socket=socket_path)
        return {**result, "created": created, "attached": attach}

    def attach(self, *, session: str, socket: str | Path) -> int:
        status = self.status(session=session, socket=socket)
        if status["running"] is not True:
            raise TmuxWorkspaceError(f"Cockpit session does not exist: {session}")
        result = self._run(
            (*self._base(Path(str(status["socket"]))), "attach-session", "-t", f"={session}")
        )
        self._require(result, "attach Cockpit session")
        return result.returncode

    def stop(self, *, session: str, socket: str | Path) -> bool:
        status = self.status(session=session, socket=socket)
        if status["running"] is not True:
            return False
        socket_path = Path(str(status["socket"]))
        self._require(
            self._run((*self._base(socket_path), "kill-session", "-t", f"={session}")),
            "stop Cockpit session",
        )
        remaining = self._run((*self._base(socket_path), "list-sessions", "-F", "#{session_name}"))
        if remaining.returncode != 0 or not remaining.stdout.strip():
            self._run((*self._base(socket_path), "kill-server"))
            socket_path.unlink(missing_ok=True)
        return True

    def open_window(
        self,
        *,
        session: str,
        socket: str | Path,
        catalog_id: str,
        command: Sequence[str],
    ) -> dict[str, object]:
        status = self.status(session=session, socket=socket)
        if status["running"] is not True:
            raise TmuxWorkspaceError(f"Cockpit session does not exist: {session}")
        socket_path = Path(str(status["socket"]))
        window = self.window_name(catalog_id)
        if window in status["windows"]:
            action = "focused"
            result = self._run(
                (*self._base(socket_path), "select-window", "-t", f"={session}:={window}")
            )
        else:
            action = "created"
            result = self._run(
                (
                    *self._base(socket_path),
                    "new-window",
                    "-t",
                    f"={session}",
                    "-n",
                    window,
                    _shell_command(command),
                )
            )
        self._require(result, f"{action} Cockpit connection window")
        return {"session": session, "window": window, "action": action}

    def layout_control(
        self,
        *,
        session: str,
        socket: str | Path,
        header_command: Sequence[str],
    ) -> None:
        session = _name(session, "session")
        socket_path = self._socket(socket)
        result = self._run(
            (
                *self._base(socket_path),
                "split-window",
                "-t",
                f"={session}:control.1",
                "-v",
                "-b",
                "-l",
                "8",
                _shell_command(header_command),
            )
        )
        self._require(result, "create Cockpit header pane")
        self._require(
            self._run((*self._base(socket_path), "select-pane", "-t", f"={session}:control.2")),
            "focus Cockpit Control body",
        )
        for target, title in (
            (f"={session}:control.1", "DIX Cockpit"),
            (f"={session}:control.2", "Daemon Catalog"),
        ):
            self._require(
                self._run((*self._base(socket_path), "select-pane", "-t", target, "-T", title)),
                "set Cockpit pane title",
            )

    def update_status(
        self,
        *,
        session: str,
        socket: str | Path,
        catalog: str,
        count: int,
        logo: str,
    ) -> None:
        session = _name(session, "session")
        socket_path = self._socket(socket)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TypeError("Cockpit daemon count must be a non-negative integer")
        if logo not in {"dix", "roba"}:
            raise ValueError("logo must be dix or roba")
        for option, value in (
            ("@cockpit-catalog", str(Path(catalog).expanduser().resolve(strict=False))),
            ("@cockpit-count", str(count)),
            ("@cockpit-logo", logo.upper()),
        ):
            self._require(
                self._run(
                    (
                        *self._base(socket_path),
                        "set-option",
                        "-t",
                        session,
                        option,
                        value,
                    )
                ),
                "update Cockpit status",
            )

    def window_name(self, catalog_id: str) -> str:
        if not isinstance(catalog_id, str) or not catalog_id.strip():
            raise TypeError("catalog_id must be a non-empty string")
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", catalog_id.strip()).strip("-.") or "daemon"
        digest = hashlib.sha256(catalog_id.encode()).hexdigest()[:8]
        value = f"connection-{slug[:24]}-{digest}"
        return _name(value, "window")

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
    def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment.pop("TMUX", None)
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
    return dict(value)


def _is_socket(path: Path) -> bool:
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except FileNotFoundError:
        return False
