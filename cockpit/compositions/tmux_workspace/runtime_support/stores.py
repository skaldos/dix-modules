from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from .lifecycle import Lifecycle
from .shared import (
    _PANE_ROLE_OPTION,
    _SELECTED_ROLES,
    _SELECTED_WINDOW_ROLE,
    _STORES_ROLES,
    _STORES_WINDOW_ROLE,
    TmuxTransport,
    TmuxWorkspaceError,
    _name,
    _shell_command,
)


class StoreWorkspaces:
    """Owned Cockpit historical dual and revisioned Store workspaces."""

    def __init__(self, tmux: TmuxTransport, lifecycle: Lifecycle) -> None:
        self._tmux = tmux
        self._lifecycle = lifecycle

    def open_window(
        self,
        *,
        session: str,
        socket: str | Path,
        catalog_id: str,
        command: Sequence[str],
    ) -> dict[str, object]:
        status = self._lifecycle.status(session=session, socket=socket)
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
            result = self._tmux._run(
                (*self._tmux._base(socket_path), "select-window", "-t", f"={session}:={window}")
            )
        else:
            action = "created"
            result = self._tmux._run(
                (
                    *self._tmux._base(socket_path),
                    "new-window",
                    "-t",
                    f"={session}",
                    "-n",
                    window,
                    _shell_command(command),
                )
            )
        self._tmux._require(result, f"{action} Cockpit connection window")
        return {"session": session, "window": window, "action": action}


    def open_stores(self, *, session: str, socket: str | Path,
                    commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        session, socket_path = self._lifecycle._owned_session(session, socket)
        if set(commands) != {"A", "B"}:
            raise ValueError("Store workspace requires exactly A and B commands")
        shell_commands = {key: _shell_command(value) for key, value in commands.items()}
        windows = self._tmux._run((*self._tmux._base(socket_path), "list-windows", "-t", f"={session}",
                             "-F", "#{window_name}\t#{@cockpit-window-role}"))
        self._tmux._require(windows, "inspect Cockpit Store window ownership")
        matches = [line.split("\t") for line in windows.stdout.splitlines()
                   if line.split("\t")[0] == "stores"]
        if matches and matches != [["stores", _STORES_WINDOW_ROLE]]:
            raise TmuxWorkspaceError("Store window is foreign or ambiguous")
        target = f"={session}:stores"
        fresh = not matches
        if fresh:
            result = self._tmux._run((*self._tmux._base(socket_path), "new-window", "-d", "-t",
                                f"={session}", "-n", "stores", "sleep 86400"))
            self._tmux._require(result, "create Cockpit Store window")
        try:
            if fresh:
                self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "set-option", "-w", "-t",
                                        target, "@cockpit-window-role", _STORES_WINDOW_ROLE)),
                              "mark Cockpit Store window")
            panes = self._tmux._panes(session, socket_path, "stores")
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
                    result = self._tmux._run((*self._tmux._base(socket_path), "split-window", "-h", "-P",
                                        "-F", "#{pane_id}", "-t", target, "sleep 86400"))
                    self._tmux._require(result, "create Cockpit Store browser pane")
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
                    self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "respawn-pane", "-k",
                                            "-t", pane["id"], shell_commands[side])),
                                  "start Cockpit Store browser")
                actions[side] = {"pane_id": pane["id"], "action": action}
            if fresh:
                self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "select-layout", "-t",
                                        target, "even-horizontal")), "layout Store browsers")
            self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "select-window", "-t", target)),
                          "focus Store window")
            self._tmux._require(self._tmux._run((*self._tmux._base(socket_path), "select-pane", "-t",
                                    actions["A"]["pane_id"])), "focus Store browser A")
            return {"session": session, "window": "stores", "panes": actions}
        except Exception:
            if fresh:
                self._tmux._run((*self._tmux._base(socket_path), "kill-window", "-t", target))
            raise


    def open_store(self, *, session: str, socket: str | Path, store_id: str,
                   revision: str, commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        import fcntl

        session, socket_path = self._lifecycle._owned_session(session, socket)
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
            self._lifecycle._owned_session(session, socket_path)
            return self._open_store(session, socket_path, store_id, revision, plans)
        finally:
            os.close(fd)


    def _open_store(self, session, socket, store_id, revision, plans):
        base = self._tmux._base(socket)
        listing = self._tmux._run((*base, "list-windows", "-t", f"={session}", "-F",
            "#{window_id}\t#{@cockpit-window-role}\t#{@cockpit-store-id}\t#{@cockpit-store-revision}\t#{@cockpit-store-session}\t#{window_linked}"))
        self._tmux._require(listing, "inspect owned Store windows")
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
            result = self._tmux._run((*base, "new-window", "-d", "-P", "-F", "#{window_id}",
                "-t", f"={session}", "-n", f"Store {store_id}", "sleep 86400"))
            self._tmux._require(result, "create owned Store window")
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
                    self._tmux._require(self._tmux._run((*base, "set-option", "-w", "-t", window, option, value)),
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
                        held = self._tmux._run((*base, "respawn-pane", "-k", "-t", old["id"], "sleep 86400"))
                        if held.returncode:
                            self._tmux._run((*base, "kill-pane", "-t", old["id"]))
                            self._tmux._require(held, "stop stale Store view")
            actions = {}
            for key, role in _SELECTED_ROLES.items():
                pane = by_role.get(role)
                if pane is None:
                    anchor = panes[0]["id"]
                    flags = ("-b",) if key == "status" else ()
                    result = self._tmux._run((*base, "split-window", "-d", "-v", *flags, "-P", "-F",
                                        "#{pane_id}", "-t", anchor, "sleep 86400"))
                    self._tmux._require(result, "create owned Store pane")
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
                    self._tmux._require(self._tmux._run((*base, "respawn-pane", "-k", "-t", pane["id"], plans[key])),
                                  "start owned Store view")
                actions[key] = {"pane_id": pane["id"], "action": action}
            if fresh or created_panes:
                self._tmux._require(self._tmux._run((*base, "select-layout", "-t", window, "even-vertical")),
                              "layout owned Store views")
            self._tmux._require(self._tmux._run((*base, "set-option", "-w", "-t", window,
                                    "@cockpit-store-revision", revision)), "commit Store window revision")
            self._tmux._require(self._tmux._run((*base, "select-window", "-t", window)), "focus owned Store window")
            self._tmux._require(self._tmux._run((*base, "select-pane", "-t", actions["browser"]["pane_id"])),
                          "focus selected Store browser")
            return {"session": session, "store_id": store_id, "revision": revision,
                    "window_id": window, "panes": actions,
                    "action": "created" if fresh else "rebuilt" if drift else
                              "repaired" if any(p["action"] != "focused" for p in actions.values()) else "focused"}
        except Exception:
            if fresh:
                self._tmux._run((*base, "kill-window", "-t", window))
            else:
                for ident in created_panes:
                    self._tmux._run((*base, "kill-pane", "-t", ident))
            raise


    def _selected_store_panes(self, socket, window):
        result = self._tmux._run((*self._tmux._base(socket), "list-panes", "-t", window, "-F",
            "#{pane_id}\t#{@cockpit-pane-role}\t#{pane_dead}\t#{@cockpit-view-store-id}\t#{@cockpit-view-store-revision}\t#{@cockpit-view-store-session}"))
        self._tmux._require(result, "inspect owned Store pane metadata")
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
            self._tmux._require(self._tmux._run((*self._tmux._base(socket), "set-option", "-p", "-t", ident, option, value)),
                          "mark selected Store pane")
        self._tmux._require(self._tmux._run((*self._tmux._base(socket), "select-pane", "-t", ident,
                                "-T", f"Store {key}")), "title selected Store pane")


    def _mark_store_pane(self, socket: Path, ident: str, side: str) -> None:
        for option, value in ((_PANE_ROLE_OPTION, _STORES_ROLES[side]),
                              ("remain-on-exit", "on")):
            self._tmux._require(self._tmux._run((*self._tmux._base(socket), "set-option", "-p", "-t", ident,
                                    option, value)), "mark Store browser pane")
        self._tmux._require(self._tmux._run((*self._tmux._base(socket), "select-pane", "-t", ident,
                                "-T", f"Stores {side} · read only")), "title Store browser")


    def window_name(self, catalog_id: str) -> str:
        if not isinstance(catalog_id, str) or not catalog_id.strip():
            raise TypeError("catalog_id must be a non-empty string")
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", catalog_id.strip()).strip("-.") or "daemon"
        digest = hashlib.sha256(catalog_id.encode()).hexdigest()[:8]
        value = f"connection-{slug[:24]}-{digest}"
        return _name(value, "window")

