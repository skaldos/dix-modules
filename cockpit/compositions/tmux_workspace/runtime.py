from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext

from .runtime_support import shared as _shared
from .runtime_support.lifecycle import Lifecycle
from .runtime_support.shared import TmuxTransport, TmuxWorkspaceError

_SESSION = _shared._SESSION
_WINDOW = _shared._WINDOW
_SOCKET_LIMIT = _shared._SOCKET_LIMIT
_SERVER_OWNER_OPTION = _shared._SERVER_OWNER_OPTION
_SERVER_OWNER_MARKER = _shared._SERVER_OWNER_MARKER
_SESSION_OWNER_OPTION = _shared._SESSION_OWNER_OPTION
_SESSION_OWNER_MARKER = _shared._SESSION_OWNER_MARKER
_PANE_ROLE_OPTION = _shared._PANE_ROLE_OPTION
_STATUS_ROLE = _shared._STATUS_ROLE
_SHELL_ROLE = _shared._SHELL_ROLE
_MASTER_ROLE = _shared._MASTER_ROLE
_STORE_ROLE = _shared._STORE_ROLE
_SELECTED_WINDOW_ROLE = _shared._SELECTED_WINDOW_ROLE
_SELECTED_ROLES = _shared._SELECTED_ROLES
_STORES_WINDOW_ROLE = _shared._STORES_WINDOW_ROLE
_STORES_ROLES = _shared._STORES_ROLES


class Runtime:
    """Explicit composition facade for one isolated Cockpit tmux server."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config
        self._transport = TmuxTransport(config)
        self._lifecycle = Lifecycle(self._transport, source_file=Path(__file__))


    def socket_path(self, runtime_root: str | Path) -> Path:
        return self._lifecycle.socket_path(runtime_root)


    def config_path(self) -> Path:
        return self._lifecycle.config_path()


    def status(self, *, session: str, socket: str | Path) -> dict[str, object]:
        return self._lifecycle.status(session=session, socket=socket)


    def start(
        self,
        *,
        session: str,
        socket: str | Path,
        control_command: Sequence[str],
        environment: Mapping[str, str],
        attach: bool = True,
    ) -> dict[str, object]:
        return self._lifecycle.start(session=session, socket=socket, control_command=control_command, environment=environment, attach=attach)


    def attach(self, *, session: str, socket: str | Path) -> int:
        return self._lifecycle.attach(session=session, socket=socket)


    def stop(self, *, session: str, socket: str | Path) -> bool:
        return self._lifecycle.stop(session=session, socket=socket)


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


    def open_master_workspace(self, *, session: str, socket: str | Path,
                              workbench_command: Sequence[str],
                              store_command: Sequence[str]) -> dict[str, object]:
        """Complete the owned master, never classify/adopt panes by title or process."""
        session, socket_path = self._owned_session(session, socket)
        _shell_command(workbench_command)
        command = _shell_command(store_command)
        panes = self._panes(session, socket_path)
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
            height = self._run((*self._base(socket_path), "display-message", "-p", "-t",
                                shell["id"], "#{pane_height}"))
            self._require(height, "measure Cockpit bottom row")
            if not height.stdout.strip().isdigit():
                raise TmuxWorkspaceError("invalid Cockpit shell height")
            result = self._run((*self._base(socket_path), "split-window", "-P", "-F",
                                "#{pane_id}", "-t", status["id"], "-v", "-l",
                                height.stdout.strip(), "sleep 86400"))
            self._require(result, "create Cockpit Store workbench pane")
            pane = {"id": result.stdout.strip(), "dead": "1"}
            if not re.fullmatch(r"%[0-9]+", pane["id"]):
                raise TmuxWorkspaceError("invalid Store workbench pane ID")
        else:
            pane = stores[0]
        action = "created" if fresh else "respawned" if pane["dead"] == "1" else "focused"
        try:
            for option, value in ((_PANE_ROLE_OPTION, _STORE_ROLE), ("remain-on-exit", "on")):
                self._require(self._run((*self._base(socket_path), "set-option", "-p", "-t",
                                        pane["id"], option, value)), "mark Cockpit Store pane")
            if action != "focused":
                self._require(self._run((*self._base(socket_path), "respawn-pane", "-k", "-t",
                                        pane["id"], command)), "start Cockpit Store workbench")
            self._require(self._run((*self._base(socket_path), "select-pane", "-t", pane["id"],
                                    "-T", "Store Workbench")), "title Cockpit Store pane")
            self._focus_master(socket_path, master["pane_id"])
        except Exception:
            if fresh:
                self._run((*self._base(socket_path), "kill-pane", "-t", pane["id"]))
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


    def open_stores(self, *, session: str, socket: str | Path,
                    commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        session, socket_path = self._owned_session(session, socket)
        if set(commands) != {"A", "B"}:
            raise ValueError("Store workspace requires exactly A and B commands")
        shell_commands = {key: _shell_command(value) for key, value in commands.items()}
        windows = self._run((*self._base(socket_path), "list-windows", "-t", f"={session}",
                             "-F", "#{window_name}\t#{@cockpit-window-role}"))
        self._require(windows, "inspect Cockpit Store window ownership")
        matches = [line.split("\t") for line in windows.stdout.splitlines()
                   if line.split("\t")[0] == "stores"]
        if matches and matches != [["stores", _STORES_WINDOW_ROLE]]:
            raise TmuxWorkspaceError("Store window is foreign or ambiguous")
        target = f"={session}:stores"
        fresh = not matches
        if fresh:
            result = self._run((*self._base(socket_path), "new-window", "-d", "-t",
                                f"={session}", "-n", "stores", "sleep 86400"))
            self._require(result, "create Cockpit Store window")
        try:
            if fresh:
                self._require(self._run((*self._base(socket_path), "set-option", "-w", "-t",
                                        target, "@cockpit-window-role", _STORES_WINDOW_ROLE)),
                              "mark Cockpit Store window")
            panes = self._panes(session, socket_path, "stores")
            if fresh:
                if len(panes) != 1:
                    raise TmuxWorkspaceError("fresh Store window has unexpected panes")
                self._mark_store_pane(socket_path, panes[0]["id"], "A")
                panes[0]["role"] = _STORES_ROLES["A"]
                # Holder is running but must be replaced below after both roles exist.
            if (len(panes) > 2 or any(p["role"] not in _STORES_ROLES.values() for p in panes)
                    or len({p["role"] for p in panes}) != len(panes)):
                raise TmuxWorkspaceError("Store pane roles are foreign or ambiguous")
            by_role = {pane["role"]: pane for pane in panes}
            actions = {}
            for side, role in _STORES_ROLES.items():
                pane = by_role.get(role)
                if pane is None:
                    result = self._run((*self._base(socket_path), "split-window", "-h", "-P",
                                        "-F", "#{pane_id}", "-t", target, "sleep 86400"))
                    self._require(result, "create Cockpit Store browser pane")
                    ident = result.stdout.strip()
                    if not re.fullmatch(r"%[0-9]+", ident):
                        raise TmuxWorkspaceError("invalid Store pane ID")
                    self._mark_store_pane(socket_path, ident, side)
                    pane = {"id": ident, "dead": "1"}
                    action = "created"
                elif fresh:
                    action = "created"
                elif pane["dead"] == "1":
                    action = "respawned"
                elif pane["dead"] == "0":
                    action = "focused"
                else:
                    raise TmuxWorkspaceError("invalid Store pane state")
                if action != "focused":
                    self._require(self._run((*self._base(socket_path), "respawn-pane", "-k",
                                            "-t", pane["id"], shell_commands[side])),
                                  "start Cockpit Store browser")
                actions[side] = {"pane_id": pane["id"], "action": action}
            if fresh:
                self._require(self._run((*self._base(socket_path), "select-layout", "-t",
                                        target, "even-horizontal")), "layout Store browsers")
            self._require(self._run((*self._base(socket_path), "select-window", "-t", target)),
                          "focus Store window")
            self._require(self._run((*self._base(socket_path), "select-pane", "-t",
                                    actions["A"]["pane_id"])), "focus Store browser A")
            return {"session": session, "window": "stores", "panes": actions}
        except Exception:
            if fresh:
                self._run((*self._base(socket_path), "kill-window", "-t", target))
            raise


    def open_store(self, *, session: str, socket: str | Path, store_id: str,
                   revision: str, commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        import fcntl

        session, socket_path = self._owned_session(session, socket)
        if (not isinstance(store_id, str) or not store_id.strip()
                or any(ord(c) < 32 for c in store_id)):
            raise ValueError("Store ID must be a non-empty single-line name")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{32}", revision):
            raise ValueError("Store revision must be opaque catalog identity")
        if set(commands) != {"status", "browser"}:
            raise ValueError("Store workspace requires status and browser commands")
        plans = {role: _shell_command(value) for role, value in commands.items()}
        fd = os.open(socket_path.parent / "store-windows.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            self._owned_session(session, socket_path)
            return self._open_store(session, socket_path, store_id, revision, plans)
        finally:
            os.close(fd)


    def _open_store(self, session, socket, store_id, revision, plans):
        base = self._base(socket)
        listing = self._run((*base, "list-windows", "-t", f"={session}", "-F",
            "#{window_id}\t#{@cockpit-window-role}\t#{@cockpit-store-id}\t#{@cockpit-store-revision}\t#{@cockpit-store-session}\t#{window_linked}"))
        self._require(listing, "inspect owned Store windows")
        matches, seen = [], set()
        for line in listing.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 6 or not re.fullmatch(r"@[0-9]+", parts[0]):
                raise TmuxWorkspaceError("invalid Store window metadata")
            ident, role, sid, rev, owner, linked = parts
            if role == _SELECTED_WINDOW_ROLE:
                if (not sid or sid in seen or owner != session or linked != "0"
                        or not re.fullmatch(r"[0-9a-f]{32}", rev)):
                    raise TmuxWorkspaceError("foreign, duplicate or inconsistent Store window metadata")
                seen.add(sid)
                if sid == store_id:
                    matches.append((ident, rev))
            elif sid or rev or owner:
                raise TmuxWorkspaceError("foreign Store window metadata")
        fresh = not matches
        created_panes = []
        if fresh:
            result = self._run((*base, "new-window", "-d", "-P", "-F", "#{window_id}",
                "-t", f"={session}", "-n", f"Store {store_id}", "sleep 86400"))
            self._require(result, "create owned Store window")
            window, previous = result.stdout.strip(), revision
            if not re.fullmatch(r"@[0-9]+", window):
                raise TmuxWorkspaceError("invalid new Store window identity")
        else:
            window, previous = matches[0]
        drift = not fresh and previous != revision
        try:
            if fresh:
                for option, value in (("@cockpit-window-role", _SELECTED_WINDOW_ROLE),
                    ("@cockpit-store-id", store_id), ("@cockpit-store-revision", revision),
                    ("@cockpit-store-session", session)):
                    self._require(self._run((*base, "set-option", "-w", "-t", window, option, value)),
                                  "mark owned Store window")
            panes = self._selected_store_panes(socket, window)
            if fresh:
                if len(panes) != 1:
                    raise TmuxWorkspaceError("fresh Store window has unexpected panes")
                self._mark_selected_pane(socket, panes[0]["id"], "status", store_id, revision, session)
                panes[0].update(role=_SELECTED_ROLES["status"], sid=store_id, rev=revision, owner=session)
            if (not panes or len(panes) > 2 or len({p["role"] for p in panes}) != len(panes)
                    or any(p["role"] not in _SELECTED_ROLES.values() or p["sid"] != store_id
                           or p["rev"] != previous or p["owner"] != session or p["dead"] not in {"0", "1"}
                           for p in panes)):
                raise TmuxWorkspaceError("foreign, duplicate or inconsistent Store pane metadata")
            by_role = {p["role"]: p for p in panes}
            if drift:
                # Stop old access first. On any subsequent failure no old browser remains live.
                for key in ("browser", "status"):
                    old = by_role.get(_SELECTED_ROLES[key])
                    if old is not None:
                        held = self._run((*base, "respawn-pane", "-k", "-t", old["id"], "sleep 86400"))
                        if held.returncode:
                            self._run((*base, "kill-pane", "-t", old["id"]))
                            self._require(held, "stop stale Store view")
            actions = {}
            for key, role in _SELECTED_ROLES.items():
                pane = by_role.get(role)
                if pane is None:
                    anchor = panes[0]["id"]
                    flags = ("-b",) if key == "status" else ()
                    result = self._run((*base, "split-window", "-d", "-v", *flags, "-P", "-F",
                                        "#{pane_id}", "-t", anchor, "sleep 86400"))
                    self._require(result, "create owned Store pane")
                    ident = result.stdout.strip()
                    if not re.fullmatch(r"%[0-9]+", ident):
                        raise TmuxWorkspaceError("invalid new Store pane identity")
                    created_panes.append(ident)
                    pane = {"id": ident, "dead": "1"}
                    action = "created"
                elif fresh:
                    action = "created"
                elif drift:
                    action = "rebuilt"
                elif pane["dead"] == "1":
                    action = "respawned"
                else:
                    action = "focused"
                if action != "focused":
                    self._mark_selected_pane(socket, pane["id"], key, store_id, revision, session)
                    self._require(self._run((*base, "respawn-pane", "-k", "-t", pane["id"], plans[key])),
                                  "start owned Store view")
                actions[key] = {"pane_id": pane["id"], "action": action}
            if fresh or created_panes:
                self._require(self._run((*base, "select-layout", "-t", window, "even-vertical")),
                              "layout owned Store views")
            self._require(self._run((*base, "set-option", "-w", "-t", window,
                                    "@cockpit-store-revision", revision)), "commit Store window revision")
            self._require(self._run((*base, "select-window", "-t", window)), "focus owned Store window")
            self._require(self._run((*base, "select-pane", "-t", actions["browser"]["pane_id"])),
                          "focus selected Store browser")
            return {"session": session, "store_id": store_id, "revision": revision,
                    "window_id": window, "panes": actions,
                    "action": "created" if fresh else "rebuilt" if drift else
                              "repaired" if any(p["action"] != "focused" for p in actions.values()) else "focused"}
        except Exception:
            if fresh:
                self._run((*base, "kill-window", "-t", window))
            else:
                for ident in created_panes:
                    self._run((*base, "kill-pane", "-t", ident))
            raise


    def _selected_store_panes(self, socket, window):
        result = self._run((*self._base(socket), "list-panes", "-t", window, "-F",
            "#{pane_id}\t#{@cockpit-pane-role}\t#{pane_dead}\t#{@cockpit-view-store-id}\t#{@cockpit-view-store-revision}\t#{@cockpit-view-store-session}"))
        self._require(result, "inspect owned Store pane metadata")
        panes = []
        for line in result.stdout.splitlines():
            values = line.split("\t")
            if len(values) != 6 or not re.fullmatch(r"%[0-9]+", values[0]):
                raise TmuxWorkspaceError("invalid Store pane metadata")
            panes.append(dict(zip(("id", "role", "dead", "sid", "rev", "owner"), values)))
        return panes


    def _mark_selected_pane(self, socket, ident, key, store_id, revision, session):
        for option, value in ((_PANE_ROLE_OPTION, _SELECTED_ROLES[key]),
            ("@cockpit-view-store-id", store_id), ("@cockpit-view-store-revision", revision),
            ("@cockpit-view-store-session", session), ("remain-on-exit", "on")):
            self._require(self._run((*self._base(socket), "set-option", "-p", "-t", ident, option, value)),
                          "mark selected Store pane")
        self._require(self._run((*self._base(socket), "select-pane", "-t", ident,
                                "-T", f"Store {key}")), "title selected Store pane")


    def _mark_store_pane(self, socket: Path, ident: str, side: str) -> None:
        for option, value in ((_PANE_ROLE_OPTION, _STORES_ROLES[side]),
                              ("remain-on-exit", "on")):
            self._require(self._run((*self._base(socket), "set-option", "-p", "-t", ident,
                                    option, value)), "mark Store browser pane")
        self._require(self._run((*self._base(socket), "select-pane", "-t", ident,
                                "-T", f"Stores {side} · read only")), "title Store browser")


    def _panes(self, session: str, socket: Path,
               window: str = "control") -> list[dict[str, str]]:
        result = self._run(
            (
                *self._base(socket),
                "list-panes",
                "-t",
                f"={session}:{window}",
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
        return self._transport._socket(value)


    def _base(self, socket: Path) -> tuple[str, ...]:
        return self._transport._base(socket)


    def _server_status(self, socket: Path) -> dict[str, bool]:
        return self._lifecycle._server_status(socket)


    def _owned_session(self, session: object, socket: str | Path) -> tuple[str, Path]:
        return self._lifecycle._owned_session(session, socket)


    def _public_status(self,
        *,
        session: str,
        socket: Path,
        server_running: bool,
        server_owned: bool,
        running: bool,
        session_owned: bool,
        windows: list[str],
    ) -> dict[str, object]:
        return self._transport._public_status(session=session, socket=socket, server_running=server_running, server_owned=server_owned, running=running, session_owned=session_owned, windows=windows)


    def _run(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        return self._transport._run(command)


    def _require(self, result: subprocess.CompletedProcess[str], operation: str) -> None:
        return self._transport._require(result, operation)


_name = _shared._name
_shell_command = _shared._shell_command
_string_environment = _shared._string_environment
_secret_key = _shared._secret_key
_is_socket = _shared._is_socket
_server_absent = _shared._server_absent
