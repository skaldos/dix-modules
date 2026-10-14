from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext

_SESSION = re.compile(r"[A-Za-z0-9_.-]+\Z")
_SOCKET_LIMIT = 107


class Runtime:
    """Resolve explicit Cockpit paths without mutating process or user state."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
    ) -> None:
        self.context = context
        self.config = config

    def defaults(self) -> dict[str, str]:
        return {
            "catalog_path": str(self.catalog_path()),
            "runtime_root": str(self.runtime_root()),
            "state_root": str(self.state_root()),
        }

    def catalog_path(self, value: str | None = None) -> Path:
        selected = value or _optional_string(self.config.get("catalog_path"))
        selected = selected or os.environ.get("DIX_COCKPIT_CATALOG")
        if selected:
            return _absolute(Path(selected))
        config_home = os.environ.get("XDG_CONFIG_HOME")
        root = Path(config_home) if config_home else Path.home() / ".config"
        return _absolute(root / "skaldos" / "cockpit" / "daemons.toml")

    def runtime_root(self, value: str | None = None) -> Path:
        selected = value or _optional_string(self.config.get("runtime_root"))
        selected = selected or os.environ.get("DIX_COCKPIT_RUNTIME_ROOT")
        if selected:
            return _absolute(Path(selected))
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg:
            return _absolute(Path(xdg) / "dix-cockpit")
        return _absolute(Path(tempfile.gettempdir()) / f"dix-cockpit-{os.getuid()}")

    def state_root(self, value: str | None = None) -> Path:
        selected = value or _optional_string(self.config.get("state_root"))
        selected = selected or os.environ.get("DIX_COCKPIT_STATE_ROOT")
        if selected:
            return _absolute(Path(selected))
        xdg = os.environ.get("XDG_STATE_HOME")
        root = Path(xdg) if xdg else Path.home() / ".local" / "state"
        return _absolute(root / "skaldos" / "cockpit")

    def session_paths(self, session: str) -> dict[str, str]:
        if not isinstance(session, str) or not session or not _SESSION.fullmatch(session):
            raise ValueError(f"Cockpit session must match {_SESSION.pattern}")
        runtime_root = self.runtime_root()
        state_root = self.state_root()
        session_runtime = runtime_root / "sessions" / session
        session_state = state_root / "sessions" / session
        roba_runtime = session_runtime / "roba"
        logs_root = session_state / "logs"
        zsh_root = session_state / "zsh"
        paths = {
            "session": session,
            "runtime_root": str(runtime_root),
            "state_root": str(state_root),
            "session_runtime_root": str(session_runtime),
            "session_state_root": str(session_state),
            "owner_file": str(session_runtime / "owner.json"),
            "roba_runtime_root": str(roba_runtime),
            "roba_logs_root": str(logs_root),
            "zsh_root": str(zsh_root),
            "history_file": str(zsh_root / "history"),
            "daemon_socket": str(roba_runtime / "daemons" / "default" / "daemon.sock"),
            "control_socket": str(roba_runtime / "daemons" / "default" / "control.sock"),
        }
        for name in ("daemon_socket", "control_socket"):
            length = len(os.fsencode(paths[name]))
            if length > _SOCKET_LIMIT:
                raise ValueError(
                    f"Cockpit {name} exceeds platform limit ({length} > {_SOCKET_LIMIT})"
                )
        return paths


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError("Cockpit path configuration must be a non-empty string")
    return value


def _absolute(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)
