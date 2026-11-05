from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from .shared import (
    _SERVER_OWNER_MARKER,
    _SERVER_OWNER_OPTION,
    _SESSION_OWNER_MARKER,
    _SESSION_OWNER_OPTION,
    _SOCKET_LIMIT,
    TmuxTransport,
    TmuxWorkspaceError,
    _is_socket,
    _name,
    _server_absent,
    _shell_command,
    _string_environment,
)


class Lifecycle:
    """Own server/session lifecycle; workspace services share this one authority."""

    def __init__(self, tmux: TmuxTransport, *, source_file: Path) -> None:
        self._tmux = tmux
        self._source_file = source_file
        self.config = tmux.config

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
        return self._source_file.parents[2] / "integrations" / "tmux" / "cockpit.conf"


    def status(self, *, session: str, socket: str | Path) -> dict[str, object]:
        session = _name(session, "session")
        socket_path = self._tmux._socket(socket)
        server = self._server_status(socket_path)
        if server["running"] is not True:
            return self._tmux._public_status(
                session=session,
                socket=socket_path,
                server_running=False,
                server_owned=False,
                running=False,
                session_owned=False,
                windows=[],
            )
        if server["owned"] is not True:
            return self._tmux._public_status(
                session=session,
                socket=socket_path,
                server_running=True,
                server_owned=False,
                running=False,
                session_owned=False,
                windows=[],
            )
        result = self._tmux._run((*self._tmux._base(socket_path), "has-session", "-t", f"={session}"))
        if result.returncode == 0:
            windows = self._tmux._run(
                (
                    *self._tmux._base(socket_path),
                    "list-windows",
                    "-t",
                    f"={session}",
                    "-F",
                    "#{window_name}",
                )
            )
            self._tmux._require(windows, "list Cockpit windows")
            owner = self._tmux._run(
                (
                    *self._tmux._base(socket_path),
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
            return self._tmux._public_status(
                session=session,
                socket=socket_path,
                server_running=True,
                server_owned=True,
                running=True,
                session_owned=session_owned,
                windows=[line for line in windows.stdout.splitlines() if line],
            )
        return self._tmux._public_status(
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
        socket_path = self._tmux._socket(socket)
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
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "select-window", "-t", f"={session}:control")),
                "focus Cockpit control window",
            )
        else:
            socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            socket_path.parent.chmod(0o700)
            start = [*self._tmux._base(socket_path)]
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
            result = self._tmux._run(tuple(start))
            self._tmux._require(result, "start Cockpit session")
            try:
                if created_server:
                    self._tmux._require(
                        self._tmux._run(
                            (
                                *self._tmux._base(socket_path),
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
                    self._tmux._require(
                        self._tmux._run(
                            (*self._tmux._base(socket_path), "set-option", "-t", session, option, value)
                        ),
                        "mark Cockpit session ownership",
                    )
            except Exception:
                if created_server:
                    self._tmux._run((*self._tmux._base(socket_path), "kill-server"))
                    if _is_socket(socket_path):
                        socket_path.unlink()
                else:
                    self._tmux._run((*self._tmux._base(socket_path), "kill-session", "-t", f"={session}"))
                raise
            created = True
        if attach:
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "attach-session", "-t", f"={session}")),
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
        result = self._tmux._run(
            (*self._tmux._base(Path(str(status["socket"]))), "attach-session", "-t", f"={session}")
        )
        self._tmux._require(result, "attach Cockpit session")
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
        self._tmux._require(
            self._tmux._run((*self._tmux._base(socket_path), "kill-session", "-t", f"={session}")),
            "stop Cockpit session",
        )
        remaining = self._tmux._run((*self._tmux._base(socket_path), "list-sessions", "-F", "#{session_name}"))
        if remaining.returncode == 0 and not remaining.stdout.strip():
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "kill-server")),
                "stop empty Cockpit tmux server",
            )
        elif remaining.returncode != 0 and not _server_absent(remaining, socket_path):
            raise TmuxWorkspaceError("cannot prove Cockpit tmux server stopped safely")
        if (remaining.returncode != 0 or not remaining.stdout.strip()) and _is_socket(socket_path):
            socket_path.unlink()
        return True


    def _server_status(self, socket: Path) -> dict[str, bool]:
        probe = self._tmux._run((*self._tmux._base(socket), "list-sessions", "-F", "#{session_name}"))
        if probe.returncode != 0:
            return {"running": not _server_absent(probe, socket), "owned": False}
        owner = self._tmux._run(
            (*self._tmux._base(socket), "show-options", "-gqv", _SERVER_OWNER_OPTION)
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

