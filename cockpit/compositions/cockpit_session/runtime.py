from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Bind Cockpit identity and paths to the isolated tmux workhorse."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        settings: Api,
        tmux: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.settings = settings
        self.tmux = tmux

    def paths(self, *, catalog: str | None = None) -> dict[str, str]:
        catalog_path = self.settings.require("catalog_path")(catalog)
        runtime_root = self.settings.require("runtime_root")()
        socket = self.tmux.require("socket_path")(runtime_root)
        tmux_config = self.tmux.require("config_path")()
        return {
            "catalog": str(catalog_path),
            "runtime_root": str(runtime_root),
            "socket": str(socket),
            "tmux_config": str(tmux_config),
        }

    def start(
        self,
        *,
        session: str = "dix",
        catalog: str | None = None,
        logo: str = "dix",
        control_command: Sequence[str],
        attach: bool = True,
    ) -> dict[str, object]:
        paths = self.paths(catalog=catalog)
        environment = {
            "DIX_COCKPIT_SESSION": session,
            "DIX_COCKPIT_CATALOG": paths["catalog"],
            "DIX_COCKPIT_LOGO": _logo(logo),
            "DIX_COCKPIT_TMUX_SOCKET": paths["socket"],
            "DIX_COCKPIT_TMUX_CONFIG": paths["tmux_config"],
        }
        result = self.tmux.require("start")(
            session=session,
            socket=paths["socket"],
            control_command=control_command,
            environment=environment,
            attach=attach,
        )
        return {**result, "catalog": paths["catalog"], "logo": logo}

    def attach(self, *, session: str = "dix") -> int:
        return self.tmux.require("attach")(session=session, socket=self.paths()["socket"])

    def status(self, *, session: str = "dix") -> dict[str, object]:
        return self.tmux.require("status")(session=session, socket=self.paths()["socket"])

    def stop(self, *, session: str = "dix") -> bool:
        return self.tmux.require("stop")(session=session, socket=self.paths()["socket"])

    def open_connection(
        self,
        *,
        session: str,
        catalog_id: str,
        command: Sequence[str],
    ) -> dict[str, object]:
        return self.tmux.require("open_window")(
            session=session,
            socket=self.paths()["socket"],
            catalog_id=catalog_id,
            command=command,
        )


def _logo(value: str) -> str:
    if value not in {"dix", "roba"}:
        raise ValueError("logo must be dix or roba")
    return value
