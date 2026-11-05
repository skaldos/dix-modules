from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext

from .runtime_support.lifecycle import Lifecycle
from .runtime_support.master import MasterWorkspace
from .runtime_support.shared import TmuxTransport
from .runtime_support.shared import (
    TmuxWorkspaceError as TmuxWorkspaceError,  # noqa: PLC0414 - public re-export
)
from .runtime_support.stores import StoreWorkspaces


class Runtime:
    """Explicit composition facade; package-local services own all tmux behavior."""

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
        self._master = MasterWorkspace(self._transport, self._lifecycle)
        self._stores = StoreWorkspaces(self._transport, self._lifecycle)


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
        return self._stores.open_window(session=session, socket=socket, catalog_id=catalog_id, command=command)


    def layout_control(
        self,
        *,
        session: str,
        socket: str | Path,
        header_command: Sequence[str],
    ) -> None:
        return self._master.layout_control(session=session, socket=socket, header_command=header_command)


    def layout_runtime(
        self,
        *,
        session: str,
        socket: str | Path,
        status_command: Sequence[str],
    ) -> None:
        return self._master.layout_runtime(session=session, socket=socket, status_command=status_command)


    def open_master_workspace(self, *, session: str, socket: str | Path,
                              workbench_command: Sequence[str],
                              store_command: Sequence[str]) -> dict[str, object]:
        return self._master.open_master_workspace(session=session, socket=socket, workbench_command=workbench_command, store_command=store_command)


    def open_master_workbench(
        self,
        *,
        session: str,
        socket: str | Path,
        command: Sequence[str],
    ) -> dict[str, str]:
        return self._master.open_master_workbench(session=session, socket=socket, command=command)


    def open_stores(self, *, session: str, socket: str | Path,
                    commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        return self._stores.open_stores(session=session, socket=socket, commands=commands)


    def open_store(self, *, session: str, socket: str | Path, store_id: str,
                   revision: str, commands: Mapping[str, Sequence[str]]) -> dict[str, object]:
        return self._stores.open_store(session=session, socket=socket, store_id=store_id, revision=revision, commands=commands)


    def update_status(
        self,
        *,
        session: str,
        socket: str | Path,
        catalog: str,
        count: int,
        logo: str,
    ) -> None:
        return self._master.update_status(session=session, socket=socket, catalog=catalog, count=count, logo=logo)


    def update_runtime_status(
        self,
        *,
        session: str,
        socket: str | Path,
        logo: str,
        daemon_state: str,
    ) -> None:
        return self._master.update_runtime_status(session=session, socket=socket, logo=logo, daemon_state=daemon_state)


    def window_name(self, catalog_id: str) -> str:
        return self._stores.window_name(catalog_id)
