from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class CockpitSessionError(RuntimeError):
    """The complete Cockpit runtime cannot be operated safely."""


class Runtime:
    """Order one private ROBA runtime and one owned session on the isolated tmux server."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        settings: Api,
        runtime: Api,
        tmux: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.settings = settings
        self.runtime = runtime
        self.tmux = tmux

    def paths(self, *, session: str = "dix", catalog: str | None = None) -> dict[str, str]:
        values = self.runtime.require("paths")(session=session)
        if not isinstance(values, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in values.items()
        ):
            raise TypeError("Cockpit runtime paths must be a string dictionary")
        socket = self.tmux.require("socket_path")(values["runtime_root"])
        result = {
            **values,
            "socket": str(socket),
            "tmux_config": str(self.tmux.require("config_path")()),
        }
        if catalog is not None:
            result["catalog"] = str(self.settings.require("catalog_path")(catalog))
        return result

    def status(self, *, session: str = "dix") -> dict[str, object]:
        paths = self.paths(session=session)
        roba = self.runtime.require("status")(session=session)
        tmux = self.tmux.require("status")(session=session, socket=paths["socket"])
        if not isinstance(roba, dict) or not isinstance(tmux, dict):
            raise TypeError("Cockpit runtime status providers must return dictionaries")
        healthy = (
            roba.get("state") == "running"
            and roba.get("owned") is True
            and tmux.get("running") is True
            and tmux.get("owned") is True
        )
        if healthy:
            state = "running"
        elif roba.get("running") is False and tmux.get("running") is False:
            state = "stopped" if roba.get("state") == "stopped" else str(roba.get("state"))
        elif roba.get("state") in {"foreign", "drift", "uncertain"} or self._tmux_unowned(
            tmux
        ):
            state = "foreign"
        else:
            state = "incomplete"
        return {
            "session": session,
            "state": state,
            "running": healthy,
            "owned": healthy,
            "runtime_root": paths["session_runtime_root"],
            "state_root": paths["session_state_root"],
            "roba": roba,
            "tmux": tmux,
        }

    def start(
        self,
        *,
        session: str = "dix",
        logo: str = "dix",
        shell_command: Sequence[str],
        status_command: Sequence[str],
        attach: bool = True,
    ) -> dict[str, object]:
        logo = _logo(logo)
        paths = self.paths(session=session)
        before_roba = self.runtime.require("status")(session=session)
        before_tmux = self.tmux.require("status")(session=session, socket=paths["socket"])
        self._guard_start(session, before_roba, before_tmux)

        roba = self.runtime.require("start")(session=session)
        tmux: dict[str, object] | None = None
        try:
            tmux_value = self.tmux.require("start")(
                session=session,
                socket=paths["socket"],
                control_command=shell_command,
                environment=self._tmux_environment(session, paths),
                attach=False,
            )
            if not isinstance(tmux_value, dict):
                raise TypeError("Cockpit tmux start must return a dictionary")
            tmux = tmux_value
            if tmux.get("created") is True:
                self.tmux.require("layout_runtime")(
                    session=session,
                    socket=paths["socket"],
                    status_command=status_command,
                )
            self.tmux.require("update_runtime_status")(
                session=session,
                socket=paths["socket"],
                logo=logo,
                daemon_state="running",
            )
        except Exception as primary_error:
            if tmux is not None and tmux.get("created") is True:
                try:
                    self.tmux.require("stop")(session=session, socket=paths["socket"])
                except RuntimeError as cleanup_error:
                    primary_error.add_note(f"Cockpit tmux cleanup failed: {cleanup_error}")
            if isinstance(roba, Mapping) and roba.get("created") is True:
                try:
                    self.runtime.require("stop")(session=session)
                except RuntimeError as cleanup_error:
                    primary_error.add_note(f"Cockpit ROBA cleanup failed: {cleanup_error}")
            raise

        if attach:
            self.tmux.require("attach")(session=session, socket=paths["socket"])
        return {
            **self.status(session=session),
            "created": {
                "roba": isinstance(roba, Mapping) and roba.get("created") is True,
                "tmux": tmux.get("created") is True,
            },
            "attached": attach,
            "logo": logo,
        }

    def attach(self, *, session: str = "dix") -> int:
        status = self.status(session=session)
        if status["running"] is not True:
            raise CockpitSessionError(
                f"Cockpit runtime is not healthy: {session}; use start or reset"
            )
        paths = self.paths(session=session)
        return self.tmux.require("attach")(session=session, socket=paths["socket"])

    def start_master(
        self,
        *,
        session: str = "dix",
        logo: str = "dix",
        shell_command: Sequence[str],
        status_command: Sequence[str],
        workbench_command: Sequence[str],
        attach: bool = True,
    ) -> dict[str, object]:
        started = self.start(
            session=session,
            logo=logo,
            shell_command=shell_command,
            status_command=status_command,
            attach=False,
        )
        try:
            workbench = self.open_master_workbench(
                session=session,
                command=workbench_command,
            )
        except Exception as primary_error:
            created = started.get("created")
            if isinstance(created, Mapping) and created.get("tmux") is True:
                paths = self.paths(session=session)
                try:
                    self.tmux.require("stop")(session=session, socket=paths["socket"])
                except RuntimeError as cleanup_error:
                    primary_error.add_note(f"Cockpit tmux cleanup failed: {cleanup_error}")
            if isinstance(created, Mapping) and created.get("roba") is True:
                try:
                    self.runtime.require("stop")(session=session)
                except RuntimeError as cleanup_error:
                    primary_error.add_note(f"Cockpit ROBA cleanup failed: {cleanup_error}")
            raise
        if attach:
            self.attach(session=session)
        return {**started, "workbench": workbench, "attached": attach}

    def open_master_workbench(
        self,
        *,
        session: str = "dix",
        command: Sequence[str],
    ) -> dict[str, str]:
        status = self.status(session=session)
        if status["running"] is not True:
            raise CockpitSessionError(
                f"Cockpit runtime is not healthy: {session}; use start or reset"
            )
        paths = self.paths(session=session)
        value = self.tmux.require("open_master_workbench")(
            session=session,
            socket=paths["socket"],
            command=command,
        )
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise TypeError("Cockpit master workbench result must be a string dictionary")
        return value

    def stop(self, *, session: str = "dix") -> dict[str, object]:
        self._guard_external_lifecycle(session, "stop")
        paths = self.paths(session=session)
        roba = self.runtime.require("status")(session=session)
        tmux = self.tmux.require("status")(session=session, socket=paths["socket"])
        self._guard_stop(session, roba, tmux)
        roba_result = self.runtime.require("stop")(session=session)
        tmux_stopped = self.tmux.require("stop")(session=session, socket=paths["socket"])
        return {
            "session": session,
            "stopped": bool(isinstance(roba_result, Mapping) and roba_result.get("stopped") is True)
            or tmux_stopped is True,
            "roba_stopped": isinstance(roba_result, Mapping) and roba_result.get("stopped") is True,
            "tmux_stopped": tmux_stopped is True,
        }

    def reset(
        self,
        *,
        session: str = "dix",
        logo: str = "dix",
        shell_command: Sequence[str],
        status_command: Sequence[str],
        attach: bool = True,
    ) -> dict[str, object]:
        self._guard_external_lifecycle(session, "reset")
        paths = self.paths(session=session)
        roba = self.runtime.require("status")(session=session)
        tmux = self.tmux.require("status")(session=session, socket=paths["socket"])
        self._guard_stop(session, roba, tmux)
        self.runtime.require("stop")(session=session)
        self.tmux.require("stop")(session=session, socket=paths["socket"])
        return self.start(
            session=session,
            logo=logo,
            shell_command=shell_command,
            status_command=status_command,
            attach=attach,
        )

    def open_connection(
        self,
        *,
        session: str,
        catalog_id: str,
        command: Sequence[str],
    ) -> dict[str, object]:
        paths = self.paths(session=session)
        return self.tmux.require("open_window")(
            session=session,
            socket=paths["socket"],
            catalog_id=catalog_id,
            command=command,
        )

    def update_status(
        self,
        *,
        session: str,
        catalog: str,
        count: int,
        logo: str,
    ) -> None:
        paths = self.paths(session=session, catalog=catalog)
        self.tmux.require("update_status")(
            session=session,
            socket=paths["socket"],
            catalog=paths["catalog"],
            count=count,
            logo=_logo(logo),
        )

    @staticmethod
    def _guard_start(session: str, roba: Mapping[str, object], tmux: Mapping[str, object]) -> None:
        if roba.get("state") == "uncertain":
            raise CockpitSessionError(
                f"ROBA runtime status is uncertain: {session}; refusing lifecycle mutation"
            )
        if Runtime._tmux_unowned(tmux):
            raise CockpitSessionError(
                f"tmux server or session is not Cockpit-owned: {session}; choose another runtime"
            )
        if tmux.get("running") is True and not (
            roba.get("state") == "running" and roba.get("owned") is True
        ):
            raise CockpitSessionError(
                f"tmux session exists but its ROBA runtime is invalid: {session}; use reset"
            )

    @staticmethod
    def _guard_stop(session: str, roba: Mapping[str, object], tmux: Mapping[str, object]) -> None:
        if roba.get("state") in {"foreign", "drift", "uncertain"}:
            raise CockpitSessionError(
                f"refusing lifecycle mutation for unowned ROBA runtime: {session}"
            )
        if Runtime._tmux_unowned(tmux):
            raise CockpitSessionError(
                f"refusing lifecycle mutation for unowned tmux server or session: {session}"
            )

    @staticmethod
    def _tmux_unowned(tmux: Mapping[str, object]) -> bool:
        return (
            tmux.get("server_running") is True and tmux.get("server_owned") is not True
        ) or (tmux.get("running") is True and tmux.get("owned") is not True)

    @staticmethod
    def _guard_external_lifecycle(session: str, operation: str) -> None:
        if os.environ.get("TMUX") and os.environ.get("DIX_COCKPIT_SESSION") == session:
            raise CockpitSessionError(
                f"refusing {operation} from inside Cockpit session {session}; detach first"
            )

    @staticmethod
    def _tmux_environment(session: str, paths: Mapping[str, str]) -> dict[str, str]:
        binary_root = Path(os.environ.get("DIX_BIN", "")) if os.environ.get("DIX_BIN") else None

        def command(name: str) -> str:
            return str(binary_root / name) if binary_root is not None else name

        return {
            "DIX_COCKPIT_SESSION": session,
            "DIX_COCKPIT_RUNTIME_ROOT": paths["runtime_root"],
            "DIX_COCKPIT_STATE_ROOT": paths["state_root"],
            "DIX_COCKPIT_TMUX_SOCKET": paths["socket"],
            "DIX_COCKPIT_TMUX_CONFIG": paths["tmux_config"],
            "DIX_COCKPIT_SHELL": command("dix-cockpit-shell"),
            "DIX_COCKPIT_CLIPBOARD_COPY": command("dix-cockpit-clipboard-copy"),
            "DIX_COCKPIT_CLIPBOARD_PASTE": command("dix-cockpit-clipboard-paste"),
        }


def _logo(value: str) -> str:
    if value not in {"dix", "roba"}:
        raise ValueError("logo must be dix or roba")
    return value
