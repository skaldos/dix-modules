from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from .lifecycle import Lifecycle
from .shared import (
    _MASTER_ROLE,
    _PANE_ROLE_OPTION,
    _SHELL_ROLE,
    _STATUS_ROLE,
    _STORE_ROLE,
    TmuxTransport,
    TmuxWorkspaceError,
    _shell_command,
)


class MasterWorkspace:
    """Owned Cockpit master panes and status."""

    def __init__(self, tmux: TmuxTransport, lifecycle: Lifecycle) -> None:
        self._tmux = tmux
        self._lifecycle = lifecycle

    def layout_control(
        self,
        *,
        session: str,
        socket: str | Path,
        header_command: Sequence[str],
    ) -> None:
        session, socket_path = self._lifecycle._owned_session(session, socket)
        result = self._tmux._run(
            (
                *self._tmux._base(socket_path),
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
        self._tmux._require(result, "create Cockpit header pane")
        self._tmux._require(
            self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t", f"={session}:control.2")),
            "focus Cockpit Control body",
        )
        for target, title in (
            (f"={session}:control.1", "DIX Cockpit"),
            (f"={session}:control.2", "Daemon Catalog"),
        ):
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t", target, "-T", title)),
                "set Cockpit pane title",
            )


    def layout_runtime(
        self,
        *,
        session: str,
        socket: str | Path,
        status_command: Sequence[str],
    ) -> None:
        session, socket_path = self._lifecycle._owned_session(session, socket)
        self._tmux._require(
            self._tmux._run(
                (
                    *self._tmux._base(socket_path),
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
        self._tmux._require(
            self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t", f"={session}:control.2")),
            "focus Cockpit owner shell",
        )
        for target, title in (
            (f"={session}:control.1", "DIX Cockpit Runtime"),
            (f"={session}:control.2", "Owner Shell"),
        ):
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t", target, "-T", title)),
                "set Cockpit runtime pane title",
            )
        for target, role in (
            (f"={session}:control.1", _STATUS_ROLE),
            (f"={session}:control.2", _SHELL_ROLE),
        ):
            self._tmux._require(
                self._tmux._run(
                    (
                        *self._tmux._base(socket_path),
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


    def open_master_workspace(self, *, session: str, socket: str | Path,
                              workbench_command: Sequence[str],
                              store_command: Sequence[str]) -> dict[str, object]:
        """Complete the owned master, never classify/adopt panes by title or process."""
        session, socket_path = self._lifecycle._owned_session(session, socket)
        _shell_command(workbench_command)
        command = _shell_command(store_command)
        panes = self._tmux._panes(session, socket_path)
        allowed = {_STATUS_ROLE, _SHELL_ROLE, _MASTER_ROLE, _STORE_ROLE}
        roles = [pane["role"] for pane in panes]
        if any(role not in allowed for role in roles) or len(set(roles)) != len(roles):
            raise TmuxWorkspaceError("foreign or ambiguous Cockpit master pane roles")
        for role in (_STATUS_ROLE, _SHELL_ROLE):
            found = [p for p in panes if p["role"] == role]
            if len(found) != 1 or found[0]["dead"] != "0":
                raise TmuxWorkspaceError("Cockpit base pane role is not healthy and unique")
        if any(p["dead"] not in {"0", "1"} for p in panes):
            raise TmuxWorkspaceError("invalid Cockpit master pane state")
        master = self.open_master_workbench(session=session, socket=socket_path,
                                            command=workbench_command)
        stores = [p for p in panes if p["role"] == _STORE_ROLE]
        fresh = not stores
        if fresh:
            status = next(p for p in panes if p["role"] == _STATUS_ROLE)
            shell = next(p for p in panes if p["role"] == _SHELL_ROLE)
            height = self._tmux._run((*self._tmux._base(socket_path), "display-message", "-p", "-t",
                                shell["id"], "#{pane_height}"))
            self._tmux._require(height, "measure Cockpit bottom row")
            if not height.stdout.strip().isdigit():
                raise TmuxWorkspaceError("invalid Cockpit shell height")
            result = self._tmux._run((*self._tmux._base(socket_path), "split-window", "-P", "-F",
                                "#{pane_id}", "-t", status["id"], "-v", "-l",
                                height.stdout.strip(), "sleep 86400"))
            self._tmux._require(result, "create Cockpit Store workbench pane")
            pane = {"id": result.stdout.strip(), "dead": "1"}
            if not re.fullmatch(r"%[0-9]+", pane["id"]):
                raise TmuxWorkspaceError("invalid Store workbench pane ID")
        else:
            pane = stores[0]
        action = "created" if fresh else "respawned" if pane["dead"] == "1" else "focused"
        try:
            for option, value in ((_PANE_ROLE_OPTION, _STORE_ROLE), ("remain-on-exit", "on")):
                self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "set-option", "-p", "-t",
                                        pane["id"], option, value)), "mark Cockpit Store pane")
            if action != "focused":
                self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "respawn-pane", "-k", "-t",
                                        pane["id"], command)), "start Cockpit Store workbench")
            self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t", pane["id"],
                                    "-T", "Store Workbench")), "title Cockpit Store pane")
            self._focus_master(socket_path, master["pane_id"])
        except Exception:
            if fresh:
                self._tmux._run((*self._tmux._base(socket_path), "kill-pane", "-t", pane["id"]))
            raise
        return {"workbench": master,
                "store": {"pane_id": pane["id"], "action": action}}


    def open_master_workbench(
        self,
        *,
        session: str,
        socket: str | Path,
        command: Sequence[str],
    ) -> dict[str, str]:
        session, socket_path = self._lifecycle._owned_session(session, socket)
        shell_command = _shell_command(command)
        panes = self._tmux._panes(session, socket_path)
        masters = [pane for pane in panes if pane["role"] == _MASTER_ROLE]
        if len(masters) > 1:
            raise TmuxWorkspaceError("Cockpit master workbench pane role is ambiguous")
        if masters:
            pane = masters[0]
            if pane["dead"] == "0":
                action = "focused"
            elif pane["dead"] == "1":
                self._tmux._require(
                    self._tmux._run(
                        (
                            *self._tmux._base(socket_path),
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
        created = self._tmux._run(
            (
                *self._tmux._base(socket_path),
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
        self._tmux._require(created, "create Cockpit master workbench pane")
        pane_id = created.stdout.strip()
        if not re.fullmatch(r"%[0-9]+", pane_id):
            raise TmuxWorkspaceError("tmux did not return a valid master workbench pane ID")
        try:
            for option, value in (
                (_PANE_ROLE_OPTION, _MASTER_ROLE),
                ("remain-on-exit", "on"),
            ):
                self._tmux._require(
                    self._tmux._run(
                        (
                            *self._tmux._base(socket_path),
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
            self._tmux._require(
                self._tmux._run(
                    (
                        *self._tmux._base(socket_path),
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
            self._tmux._run((*self._tmux._base(socket_path), "kill-pane", "-t", pane_id))
            raise
        return {"session": session, "pane_id": pane_id, "action": "created"}


    def _focus_master(self, socket: Path, pane_id: str) -> None:
        self._tmux._require(
            self._tmux._run((*self._tmux._base(socket), "select-pane", "-t", pane_id, "-T", "ROBA Loom")),
            "title Cockpit master workbench pane",
        )
        self._tmux._require(
            self._tmux._run((*self._tmux._base(socket), "select-pane", "-t", pane_id)),
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
        session, socket_path = self._lifecycle._owned_session(session, socket)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise TypeError("Cockpit daemon count must be a non-negative integer")
        if logo not in {"dix", "roba"}:
            raise ValueError("logo must be dix or roba")
        for option, value in (
            ("@cockpit-catalog", str(Path(catalog).expanduser().resolve(strict=False))),
            ("@cockpit-count", str(count)),
            ("@cockpit-logo", logo.upper()),
        ):
            self._tmux._require(
                self._tmux._run(
                    (
                        *self._tmux._base(socket_path),
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
        session, socket_path = self._lifecycle._owned_session(session, socket)
        if logo not in {"dix", "roba"}:
            raise ValueError("logo must be dix or roba")
        if not isinstance(daemon_state, str) or not daemon_state:
            raise TypeError("daemon_state must be a non-empty string")
        for option, value in (
            ("@cockpit-logo", logo.upper()),
            ("@cockpit-daemon-state", daemon_state),
        ):
            self._tmux._require(
                self._tmux._run((*self._tmux._base(socket_path), "set-option", "-t", session, option, value)),
                "update Cockpit runtime status",
            )

