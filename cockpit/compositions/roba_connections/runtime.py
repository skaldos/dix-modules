from __future__ import annotations

import copy
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext

_ENTRY_FIELDS = {"catalog_id", "daemon_id", "runtime_root", "logs_root", "timeout"}


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Resolve catalog entries through existing DIX-ROBA capabilities in-process."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        daemon: Api,
        control: Api,
        loom: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.daemon = daemon
        self.control = control
        self.loom = loom

    def resolve(self, entry: Mapping[str, object]) -> dict[str, object]:
        values = _entry(entry)
        basic = {key: values[key] for key in ("daemon_id", "runtime_root", "logs_root", "timeout")}
        endpoint = (
            Path(str(values["runtime_root"]))
            / "daemons"
            / str(values["daemon_id"])
            / "daemon.sock"
        )
        runtime_directory = endpoint.parent
        if not runtime_directory.exists():
            return _result(values, "stopped", self._connection(basic))
        if not endpoint.exists():
            return _error(values, f"daemon runtime exists without endpoint: {runtime_directory}")
        try:
            self._configure(self.daemon, basic)
            status = self.daemon.require("status")()
            if not isinstance(status, Mapping):
                raise TypeError("ROBA daemon status must return a mapping")
            if status.get("daemon_id") != values["daemon_id"]:
                raise RuntimeError("ROBA daemon endpoint reported a different daemon_id")
            self._configure(self.control, basic)
            credentials = self.control.require("credentials")()
            if not isinstance(credentials, Mapping):
                raise TypeError("DIX control credentials must return a mapping")
            capability = {
                **basic,
                "pid": _integer(status, "pid"),
                "daemon_socket": _string(status, "daemon_socket"),
                "control_socket": _string(status, "control_socket"),
                "control_token": _string(credentials, "control_token"),
            }
            return _result(values, "running", self._connection(capability), status=dict(status))
        except Exception as exc:  # noqa: BLE001 - the per-row provider error is product data
            return _error(values, f"{type(exc).__name__}: {exc}")

    def resolve_all(self, entries: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
        if isinstance(entries, (str, bytes, bytearray)):
            raise TypeError("catalog entries must be a sequence of mappings")
        return [self.resolve(entry) for entry in entries]

    def _connection(self, value: Mapping[str, object]) -> dict[str, object]:
        result = self.loom.require("materialize_connection")(dict(value))
        if not isinstance(result, dict):
            raise TypeError("ROBA Loom must materialize one connection mapping")
        return copy.deepcopy(result)

    @staticmethod
    def _configure(api: Api, values: Mapping[str, object]) -> None:
        changed = api.require("set")(dict(values))
        if type(changed) is not bool:
            raise TypeError("ROBA configuration set must return a boolean")


def _entry(value: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping) or set(value) != _ENTRY_FIELDS:
        raise TypeError("catalog entry must contain exactly catalog_id and ROBA daemon config")
    catalog_id = _string(value, "catalog_id")
    daemon_id = _string(value, "daemon_id")
    runtime_root = _string(value, "runtime_root")
    logs_root = _string(value, "logs_root")
    timeout = value.get("timeout")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or float(timeout) <= 0:
        raise TypeError("catalog entry timeout must be a positive number")
    return {
        "catalog_id": catalog_id,
        "daemon_id": daemon_id,
        "runtime_root": runtime_root,
        "logs_root": logs_root,
        "timeout": float(timeout),
    }


def _result(
    entry: Mapping[str, object],
    state: str,
    connection: Mapping[str, object],
    *,
    status: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        **entry,
        "state": state,
        "connection": copy.deepcopy(dict(connection)),
        "daemon_status": copy.deepcopy(dict(status)) if status is not None else None,
        "error": None,
    }


def _error(entry: Mapping[str, object], message: str) -> dict[str, object]:
    return {
        **entry,
        "state": "error",
        "connection": None,
        "daemon_status": None,
        "error": message,
    }


def _string(values: Mapping[str, object], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")
    return value


def _integer(values: Mapping[str, object], name: str) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value
