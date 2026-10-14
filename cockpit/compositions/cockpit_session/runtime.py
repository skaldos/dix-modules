from __future__ import annotations

import os
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
        header_command: Sequence[str],
        count: int,
        attach: bool = True,
    ) -> dict[str, object]:
        paths = self.paths(catalog=catalog)
        environment = {
            "DIX_COCKPIT_SESSION": session,
            "DIX_COCKPIT_CATALOG": paths["catalog"],
            "DIX_COCKPIT_LOGO": _logo(logo),
            "DIX_COCKPIT_TMUX_SOCKET": paths["socket"],
            "DIX_COCKPIT_TMUX_CONFIG": paths["tmux_config"],
            "DIX_COCKPIT_CLIPBOARD_COPY": os.environ.get(
                "DIX_COCKPIT_CLIPBOARD_COPY", "dix-cockpit-clipboard-copy"
            ),
            "DIX_COCKPIT_CLIPBOARD_PASTE": os.environ.get(
                "DIX_COCKPIT_CLIPBOARD_PASTE", "dix-cockpit-clipboard-paste"
            ),
        }
        result = self.tmux.require("start")(
            session=session,
            socket=paths["socket"],
            control_command=control_command,
            environment=environment,
            attach=False,
        )
        if result.get("created") is True:
            self.tmux.require("layout_control")(
                session=session,
                socket=paths["socket"],
                header_command=header_command,
            )
        self.tmux.require("update_status")(
            session=session,
            socket=paths["socket"],
            catalog=paths["catalog"],
            count=count,
            logo=logo,
        )
        if attach:
            self.tmux.require("attach")(session=session, socket=paths["socket"])
        return {
            **result,
            "attached": attach,
            "catalog": paths["catalog"],
            "logo": logo,
        }

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

    def update_status(
        self,
        *,
        session: str,
        catalog: str,
        count: int,
        logo: str,
    ) -> None:
        paths = self.paths(catalog=catalog)
        self.tmux.require("update_status")(
            session=session,
            socket=paths["socket"],
            catalog=paths["catalog"],
            count=count,
            logo=_logo(logo),
        )


def _logo(value: str) -> str:
    if value not in {"dix", "roba"}:
        raise ValueError("logo must be dix or roba")
    return value
