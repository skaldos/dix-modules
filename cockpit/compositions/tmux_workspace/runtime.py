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
_SERVER_OWNER_OPTION = "@cockpit-server-owner"
_SERVER_OWNER_MARKER = "skaldos.dix-cockpit.tmux-server.v1"
_SESSION_OWNER_OPTION = "@cockpit-owner"
_SESSION_OWNER_MARKER = "skaldos.dix-cockpit.tmux-session.v1"
_PANE_ROLE_OPTION = "@cockpit-pane-role"
_STATUS_ROLE = "skaldos.dix-cockpit.runtime-status.v1"
_SHELL_ROLE = "skaldos.dix-cockpit.owner-shell.v1"
_MASTER_ROLE = "skaldos.dix-cockpit.master-workbench.v1"


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
        server = self._server_status(socket_path)
        if server["running"] is not True:
            return self._public_status(
                session=session,
                socket=socket_path,
                server_running=False,
                server_owned=False,
                running=False,
                session_owned=False,
                windows=[],
            )
        if server["owned"] is not True:
            return self._public_status(
                session=session,
                socket=socket_path,
                server_running=True,
                server_owned=False,
                running=False,
                session_owned=False,
                windows=[],
            )
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
            owner = self._run(
                (
                    *self._base(socket_path),
                    "show-options",
                    "-v",
                    "-t",
                    session,
                    _SESSION_OWNER_OPTION,
                )
            )
            session_owned = (
                owner.returncode == 0 and owner.stdout.strip() == _SESSION_OWNER_MARKER
            )
            return self._public_status(
                session=session,
                socket=socket_path,
                server_running=True,
                server_owned=True,
                running=True,
                session_owned=session_owned,
                windows=[line for line in windows.stdout.splitlines() if line],
            )
        return self._public_status(
            session=session,
            socket=socket_path,
            server_running=True,
            server_owned=True,
            running=False,
            session_owned=False,
            windows=[],
        )

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
        created_server = False
        if current["server_running"] is True and current["server_owned"] is not True:
            raise TmuxWorkspaceError(
                f"refusing to reuse a tmux server without Cockpit ownership: {socket_path}"
            )
        if current["running"] is True:
            if current["owned"] is not True:
                raise TmuxWorkspaceError(
                    f"refusing to reuse a tmux session without Cockpit ownership: {session}"
                )
            self._require(
                self._run((*self._base(socket_path), "select-window", "-t", f"={session}:control")),
                "focus Cockpit control window",
            )
        else:
            socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            socket_path.parent.chmod(0o700)
            start = [*self._base(socket_path)]
            if current["server_running"] is not True:
                if socket_path.exists() or socket_path.is_symlink():
                    if not _is_socket(socket_path):
                        raise TmuxWorkspaceError(
                            f"refusing to replace non-socket tmux endpoint: {socket_path}"
                        )
                    socket_path.unlink()
                config = self.config_path()
                if not config.is_file():
                    raise TmuxWorkspaceError(f"Cockpit tmux config does not exist: {config}")
                start.extend(("-f", str(config)))
                created_server = True
            start.extend(("new-session", "-d", "-s", session, "-n", "control"))
            for key, value in env.items():
                start.extend(("-e", f"{key}={value}"))
            start.append(command)
            result = self._run(tuple(start))
            self._require(result, "start Cockpit session")
            try:
                if created_server:
                    self._require(
                        self._run(
                            (
                                *self._base(socket_path),
                                "set-option",
                                "-g",
                                _SERVER_OWNER_OPTION,
                                _SERVER_OWNER_MARKER,
                            )
                        ),
                        "mark Cockpit tmux server ownership",
                    )
                for option, value in (
                    (_SESSION_OWNER_OPTION, _SESSION_OWNER_MARKER),
                    ("@cockpit-session", session),
                ):
                    self._require(
                        self._run(
                            (*self._base(socket_path), "set-option", "-t", session, option, value)
                        ),
                        "mark Cockpit session ownership",
                    )
            except Exception:
                if created_server:
                    self._run((*self._base(socket_path), "kill-server"))
                    if _is_socket(socket_path):
                        socket_path.unlink()
                else:
                    self._run((*self._base(socket_path), "kill-session", "-t", f"={session}"))
                raise
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
        if status["server_running"] is True and status["server_owned"] is not True:
            raise TmuxWorkspaceError("refusing to attach through an unowned tmux server")
        if status["running"] is not True:
            raise TmuxWorkspaceError(f"Cockpit session does not exist: {session}")
        if status["owned"] is not True:
            raise TmuxWorkspaceError(
                f"refusing to attach a tmux session without Cockpit ownership: {session}"
            )
        result = self._run(
            (*self._base(Path(str(status["socket"]))), "attach-session", "-t", f"={session}")
        )
        self._require(result, "attach Cockpit session")
        return result.returncode

    def stop(self, *, session: str, socket: str | Path) -> bool:
        status = self.status(session=session, socket=socket)
        if status["server_running"] is True and status["server_owned"] is not True:
            raise TmuxWorkspaceError("refusing to stop through an unowned tmux server")
        if status["running"] is not True:
            return False
        if status["owned"] is not True:
            raise TmuxWorkspaceError(
                f"refusing to stop a tmux session without Cockpit ownership: {session}"
            )
        socket_path = Path(str(status["socket"]))
        self._require(
            self._run((*self._base(socket_path), "kill-session", "-t", f"={session}")),
            "stop Cockpit session",
        )
        remaining = self._run((*self._base(socket_path), "list-sessions", "-F", "#{session_name}"))
        if remaining.returncode == 0 and not remaining.stdout.strip():
            self._require(
                self._run((*self._base(socket_path), "kill-server")),
                "stop empty Cockpit tmux server",
            )
        elif remaining.returncode != 0 and not _server_absent(remaining, socket_path):
            raise TmuxWorkspaceError("cannot prove Cockpit tmux server stopped safely")
        if (remaining.returncode != 0 or not remaining.stdout.strip()) and _is_socket(socket_path):
            socket_path.unlink()
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
        if status["server_running"] is True and status["server_owned"] is not True:
            raise TmuxWorkspaceError("refusing to mutate an unowned tmux server")
        if status["running"] is not True:
            raise TmuxWorkspaceError(f"Cockpit session does not exist: {session}")
        if status["owned"] is not True:
            raise TmuxWorkspaceError(
                f"refusing to mutate a tmux session without Cockpit ownership: {session}"
            )
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
        session, socket_path = self._owned_session(session, socket)
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

    def layout_runtime(
        self,
        *,
        session: str,
        socket: str | Path,
        status_command: Sequence[str],
    ) -> None:
        session, socket_path = self._owned_session(session, socket)
        self._require(
            self._run(
                (
                    *self._base(socket_path),
                    "split-window",
                    "-t",
                    f"={session}:control.1",
                    "-h",
                    "-b",
                    "-l",
                    "38%",
                    _shell_command(status_command),
                )
            ),
            "create Cockpit logo/status pane",
        )
        self._require(
            self._run((*self._base(socket_path), "select-pane", "-t", f"={session}:control.2")),
            "focus Cockpit owner shell",
        )
        for target, title in (
            (f"={session}:control.1", "DIX Cockpit Runtime"),
            (f"={session}:control.2", "Owner Shell"),
        ):
            self._require(
                self._run((*self._base(socket_path), "select-pane", "-t", target, "-T", title)),
                "set Cockpit runtime pane title",
            )
        for target, role in (
            (f"={session}:control.1", _STATUS_ROLE),
            (f"={session}:control.2", _SHELL_ROLE),
        ):
            self._require(
                self._run(
                    (
                        *self._base(socket_path),
                        "set-option",
                        "-p",
                        "-t",
                        target,
                        _PANE_ROLE_OPTION,
                        role,
                    )
                ),
                "mark Cockpit runtime pane role",
            )

    def open_master_workbench(
        self,
        *,
        session: str,
        socket: str | Path,
        command: Sequence[str],
    ) -> dict[str, str]:
        session, socket_path = self._owned_session(session, socket)
        shell_command = _shell_command(command)
        panes = self._panes(session, socket_path)
        masters = [pane for pane in panes if pane["role"] == _MASTER_ROLE]
        if len(masters) > 1:
            raise TmuxWorkspaceError("Cockpit master workbench pane role is ambiguous")
        if masters:
            pane = masters[0]
            if pane["dead"] == "0":
                action = "focused"
            elif pane["dead"] == "1":
                self._require(
                    self._run(
                        (
                            *self._base(socket_path),
                            "respawn-pane",
                            "-k",
                            "-t",
                            pane["id"],
                            shell_command,
                        )
                    ),
                    "respawn Cockpit master workbench",
                )
                action = "respawned"
            else:
                raise TmuxWorkspaceError("Cockpit master workbench has invalid pane state")
            self._focus_master(socket_path, pane["id"])
            return {"session": session, "pane_id": pane["id"], "action": action}

        shells = [pane for pane in panes if pane["role"] == _SHELL_ROLE]
        if len(shells) != 1 or shells[0]["dead"] != "0":
            raise TmuxWorkspaceError("Cockpit owner shell pane role is not healthy and unique")
        created = self._run(
            (
                *self._base(socket_path),
                "split-window",
                "-P",
                "-F",
                "#{pane_id}",
                "-t",
                shells[0]["id"],
                "-v",
                "-b",
                "-p",
                "72",
                "sleep 86400",
            )
        )
        self._require(created, "create Cockpit master workbench pane")
        pane_id = created.stdout.strip()
        if not re.fullmatch(r"%[0-9]+", pane_id):
            raise TmuxWorkspaceError("tmux did not return a valid master workbench pane ID")
        try:
            for option, value in (
                (_PANE_ROLE_OPTION, _MASTER_ROLE),
                ("remain-on-exit", "on"),
            ):
                self._require(
                    self._run(
                        (
                            *self._base(socket_path),
                            "set-option",
                            "-p",
                            "-t",
                            pane_id,
                            option,
                            value,
                        )
                    ),
                    "configure Cockpit master workbench pane",
                )
            self._require(
                self._run(
                    (
                        *self._base(socket_path),
                        "respawn-pane",
                        "-k",
                        "-t",
                        pane_id,
                        shell_command,
                    )
                ),
                "start Cockpit master workbench",
            )
            self._focus_master(socket_path, pane_id)
        except Exception:
            self._run((*self._base(socket_path), "kill-pane", "-t", pane_id))
            raise
        return {"session": session, "pane_id": pane_id, "action": "created"}

    def _panes(self, session: str, socket: Path) -> list[dict[str, str]]:
        result = self._run(
            (
                *self._base(socket),
                "list-panes",
                "-t",
                f"={session}:control",
                "-F",
                f"#{{pane_id}}\t#{{{_PANE_ROLE_OPTION}}}\t#{{pane_dead}}",
            )
        )
        self._require(result, "list Cockpit control panes")
        panes: list[dict[str, str]] = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) != 3 or not re.fullmatch(r"%[0-9]+", fields[0]):
                raise TmuxWorkspaceError("tmux returned invalid Cockpit pane metadata")
            panes.append({"id": fields[0], "role": fields[1], "dead": fields[2]})
        return panes

    def _focus_master(self, socket: Path, pane_id: str) -> None:
        self._require(
            self._run((*self._base(socket), "select-pane", "-t", pane_id, "-T", "ROBA Loom")),
            "title Cockpit master workbench pane",
        )
        self._require(
            self._run((*self._base(socket), "select-pane", "-t", pane_id)),
            "focus Cockpit master workbench pane",
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
        session, socket_path = self._owned_session(session, socket)
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

    def update_runtime_status(
        self,
        *,
        session: str,
        socket: str | Path,
        logo: str,
        daemon_state: str,
    ) -> None:
        session, socket_path = self._owned_session(session, socket)
        if logo not in {"dix", "roba"}:
            raise ValueError("logo must be dix or roba")
        if not isinstance(daemon_state, str) or not daemon_state:
            raise TypeError("daemon_state must be a non-empty string")
        for option, value in (
            ("@cockpit-logo", logo.upper()),
            ("@cockpit-daemon-state", daemon_state),
        ):
            self._require(
                self._run((*self._base(socket_path), "set-option", "-t", session, option, value)),
                "update Cockpit runtime status",
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

    def _server_status(self, socket: Path) -> dict[str, bool]:
        probe = self._run((*self._base(socket), "list-sessions", "-F", "#{session_name}"))
        if probe.returncode != 0:
            return {"running": not _server_absent(probe, socket), "owned": False}
        owner = self._run(
            (*self._base(socket), "show-options", "-gqv", _SERVER_OWNER_OPTION)
        )
        return {
            "running": True,
            "owned": owner.returncode == 0 and owner.stdout.strip() == _SERVER_OWNER_MARKER,
        }

    def _owned_session(self, session: object, socket: str | Path) -> tuple[str, Path]:
        name = _name(session, "session")
        status = self.status(session=name, socket=socket)
        if status["running"] is not True or status["owned"] is not True:
            raise TmuxWorkspaceError(f"Cockpit session is not provably owned: {name}")
        return name, Path(str(status["socket"]))

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
