from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from dix.core.composition import CompositionRuntimeContext
from roba import ControlApi, ControlLocator, TransportClient

_MARKER = "skaldos.dix-cockpit.runtime.v1"
_DAEMON_ID = "default"
_OWNER_FIELDS = {
    "version",
    "owner",
    "session",
    "daemon_id",
    "runtime_root",
    "logs_root",
    "daemon_socket",
    "control_socket",
    "daemon_locator",
    "control_locator",
    "pid",
    "control_token",
}


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class CockpitRuntimeError(RuntimeError):
    """One named Cockpit runtime is absent, inconsistent or not provably owned."""


class Runtime:
    """Own one private ROBA lifecycle without DIX Control or credential recovery."""

    def __init__(
        self,
        *,
        context: CompositionRuntimeContext,
        config: Mapping[str, object],
        settings: Api,
        daemon: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.settings = settings
        self.daemon = daemon

    def paths(self, *, session: str = "dix") -> dict[str, str]:
        value = self.settings.require("session_paths")(session)
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise TypeError("Cockpit session paths must be a string dictionary")
        return value

    def status(self, *, session: str = "dix") -> dict[str, object]:
        paths = self.paths(session=session)
        try:
            daemon_status = self._probe(paths)
        except CockpitRuntimeError:
            return self._public_status(
                paths,
                state="uncertain",
                running=False,
                owned=False,
                pid=None,
            )
        owner_path = Path(paths["owner_file"])
        if daemon_status is None:
            return self._public_status(
                paths,
                state="stale" if owner_path.exists() else "stopped",
                running=False,
                owned=False,
                pid=None,
            )
        pid = _pid(daemon_status.get("pid"))
        if not owner_path.exists():
            return self._public_status(paths, state="foreign", running=True, owned=False, pid=pid)
        try:
            owner = self._owner(paths)
            self._validate_live_owner(paths, owner, daemon_status)
        except (CockpitRuntimeError, TypeError, ValueError):
            return self._public_status(paths, state="drift", running=True, owned=False, pid=pid)
        return self._public_status(paths, state="running", running=True, owned=True, pid=pid)

    def start(self, *, session: str = "dix") -> dict[str, object]:
        paths = self.paths(session=session)
        daemon_status = self._probe(paths)
        owner_path = Path(paths["owner_file"])
        if daemon_status is not None:
            if not owner_path.exists():
                raise CockpitRuntimeError(
                    "ROBA daemon is already running without Cockpit ownership; use another session"
                )
            owner = self._owner(paths)
            self._validate_live_owner(paths, owner, daemon_status)
            return {
                **self._public_status(
                    paths,
                    state="running",
                    running=True,
                    owned=True,
                    pid=_pid(daemon_status.get("pid")),
                ),
                "created": False,
            }

        self._remove_stale(paths)
        self._prepare(paths)
        creation: object | None = None
        try:
            self._configure(paths)
            creation = self.daemon.require("start")()
            owner = self._creation_owner(paths, creation)
            self._write_owner(owner_path, owner)
            current = self._probe(paths)
            if current is None:
                raise CockpitRuntimeError("new Cockpit ROBA daemon is not reachable")
            self._validate_live_owner(paths, owner, current)
            return {
                **self._public_status(
                    paths,
                    state="running",
                    running=True,
                    owned=True,
                    pid=_pid(current.get("pid")),
                ),
                "created": True,
            }
        except Exception as primary_error:
            if creation is not None:
                try:
                    self.daemon.require("stop")()
                except RuntimeError as cleanup_error:
                    primary_error.add_note(f"Cockpit daemon cleanup failed: {cleanup_error}")
            shutil.rmtree(paths["session_runtime_root"], ignore_errors=True)
            raise

    def stop(self, *, session: str = "dix") -> dict[str, object]:
        paths = self.paths(session=session)
        daemon_status = self._probe(paths)
        owner_path = Path(paths["owner_file"])
        if daemon_status is None:
            self._remove_stale(paths)
            return {
                **self._public_status(paths, state="stopped", running=False, owned=False, pid=None),
                "stopped": False,
            }
        if not owner_path.exists():
            raise CockpitRuntimeError("refusing to stop a ROBA daemon without Cockpit ownership")
        owner = self._owner(paths)
        self._validate_live_owner(paths, owner, daemon_status)
        self._configure(paths)
        self.daemon.require("stop")()
        shutil.rmtree(paths["session_runtime_root"], ignore_errors=True)
        return {
            **self._public_status(paths, state="stopped", running=False, owned=False, pid=None),
            "stopped": True,
        }

    def owner_environment(self, *, session: str = "dix") -> dict[str, str]:
        paths = self.paths(session=session)
        daemon_status = self._probe(paths)
        if daemon_status is None:
            raise CockpitRuntimeError(f"Cockpit runtime is not running: {session}")
        owner = self._owner(paths)
        self._validate_live_owner(paths, owner, daemon_status)
        return {
            "DIX_COCKPIT_SESSION": session,
            "DIX_COCKPIT_RUNTIME_ROOT": paths["runtime_root"],
            "DIX_COCKPIT_STATE_ROOT": paths["state_root"],
            "DIX_ROBA_RUNTIME_ROOT": paths["roba_runtime_root"],
            "DIX_ROBA_LOGS_ROOT": paths["roba_logs_root"],
            "ROBA_RUNTIME_ROOT": paths["roba_runtime_root"],
            "ROBA_LOGS_ROOT": paths["roba_logs_root"],
            "ROBA_DAEMON": str(owner["daemon_locator"]),
            "ROBA_CONTROL": str(owner["control_locator"]),
            "ROBA_CONTROL_TOKEN": str(owner["control_token"]),
        }

    def _configure(self, paths: Mapping[str, str]) -> None:
        changed = self.daemon.require("set")(
            {
                "daemon_id": _DAEMON_ID,
                "runtime_root": paths["roba_runtime_root"],
                "logs_root": paths["roba_logs_root"],
                "timeout": _timeout(self.config.get("timeout", 5.0)),
            }
        )
        if type(changed) is not bool:
            raise TypeError("ROBA daemon config set must return a boolean")

    def _probe(self, paths: Mapping[str, str]) -> dict[str, object] | None:
        self._configure(paths)
        try:
            value = self.daemon.require("status")()
        except RuntimeError as exc:
            endpoints = self._existing_endpoints(paths)
            if endpoints:
                joined = ", ".join(str(path) for path in endpoints)
                raise CockpitRuntimeError(
                    "ROBA status failed while expected runtime endpoints still exist: " + joined
                ) from exc
            return None
        if not isinstance(value, dict):
            raise TypeError("ROBA daemon status must return a dictionary")
        return value

    @staticmethod
    def _existing_endpoints(paths: Mapping[str, str]) -> tuple[Path, ...]:
        existing: list[Path] = []
        for name in ("daemon_socket", "control_socket"):
            path = Path(paths[name])
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise CockpitRuntimeError(
                    f"cannot inspect expected ROBA runtime endpoint: {path}"
                ) from exc
            existing.append(path)
        return tuple(existing)

    def _owner(self, paths: Mapping[str, str]) -> dict[str, object]:
        path = Path(paths["owner_file"])
        try:
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise CockpitRuntimeError("Cockpit owner artifact is missing") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise CockpitRuntimeError("Cockpit owner artifact must be a regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise CockpitRuntimeError("Cockpit owner artifact must have mode 0600")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CockpitRuntimeError("Cockpit owner artifact is invalid") from exc
        if not isinstance(value, dict) or set(value) != _OWNER_FIELDS:
            raise CockpitRuntimeError("Cockpit owner artifact has an invalid schema")
        return value

    def _creation_owner(self, paths: Mapping[str, str], creation: object) -> dict[str, object]:
        values = {
            "version": 1,
            "owner": _MARKER,
            "session": paths["session"],
            "daemon_id": _required_creation(creation, "daemon_id"),
            "runtime_root": paths["roba_runtime_root"],
            "logs_root": paths["roba_logs_root"],
            "daemon_socket": str(_required_creation(creation, "daemon_socket")),
            "control_socket": str(_required_creation(creation, "control_socket")),
            "daemon_locator": str(_required_creation(creation, "daemon_locator")),
            "control_locator": str(_required_creation(creation, "control_locator")),
            "pid": _pid(_required_creation(creation, "pid")),
            "control_token": _required_creation(creation, "control_token"),
        }
        if values["daemon_id"] != _DAEMON_ID:
            raise CockpitRuntimeError("new ROBA daemon returned the wrong identity")
        return values

    def _validate_live_owner(
        self,
        paths: Mapping[str, str],
        owner: Mapping[str, object],
        daemon_status: Mapping[str, object],
    ) -> None:
        expected = {
            "version": 1,
            "owner": _MARKER,
            "session": paths["session"],
            "daemon_id": _DAEMON_ID,
            "runtime_root": paths["roba_runtime_root"],
            "logs_root": paths["roba_logs_root"],
            "daemon_socket": paths["daemon_socket"],
            "control_socket": paths["control_socket"],
            "daemon_locator": "id:default",
            "control_locator": "id:default",
        }
        if any(owner.get(key) != value for key, value in expected.items()):
            raise CockpitRuntimeError("Cockpit owner artifact does not match this runtime")
        if _pid(owner.get("pid")) != _pid(daemon_status.get("pid")):
            raise CockpitRuntimeError("Cockpit owner process identity does not match")
        token = owner.get("control_token")
        if not isinstance(token, str) or not token:
            raise CockpitRuntimeError("Cockpit Control capability is missing")
        try:
            ControlApi(
                transport=TransportClient(
                    socket=Path(paths["control_socket"]),
                    timeout=_timeout(self.config.get("timeout", 5.0)),
                ),
                token=token,
                locator=ControlLocator("id", _DAEMON_ID),
            ).contexts()
        except Exception as exc:
            raise CockpitRuntimeError("Cockpit Control capability is not valid") from exc

    @staticmethod
    def _public_status(
        paths: Mapping[str, str],
        *,
        state: str,
        running: bool,
        owned: bool,
        pid: int | None,
    ) -> dict[str, object]:
        return {
            "session": paths["session"],
            "state": state,
            "running": running,
            "owned": owned,
            "daemon_id": _DAEMON_ID,
            "pid": pid,
            "runtime_root": paths["roba_runtime_root"],
            "logs_root": paths["roba_logs_root"],
            "daemon_locator": "id:default",
            "control_locator": "id:default",
            "owner_file": paths["owner_file"],
        }

    @staticmethod
    def _prepare(paths: Mapping[str, str]) -> None:
        for name in (
            "runtime_root",
            "session_runtime_root",
            "state_root",
            "session_state_root",
            "roba_logs_root",
        ):
            path = Path(paths[name])
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.chmod(0o700)

    @staticmethod
    def _remove_stale(paths: Mapping[str, str]) -> None:
        shutil.rmtree(paths["session_runtime_root"], ignore_errors=True)

    @staticmethod
    def _write_owner(path: Path, value: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".owner-", dir=path.parent)
        temporary_path = Path(temporary)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                json.dump(value, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            path.chmod(0o600)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)


def _required_creation(value: object, name: str) -> object:
    result = getattr(value, name, None)
    if result is None or result == "":
        raise CockpitRuntimeError(f"ROBA creation result is missing {name}")
    return result


def _pid(value: object) -> int:
    if isinstance(value, bool):
        raise CockpitRuntimeError("ROBA daemon PID is invalid")
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CockpitRuntimeError("ROBA daemon PID is invalid") from exc
    if result <= 0:
        raise CockpitRuntimeError("ROBA daemon PID is invalid")
    return result


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise TypeError("Cockpit ROBA timeout must be a positive number")
    return float(value)
