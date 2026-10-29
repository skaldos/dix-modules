from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Bind the generic workbench to one live Cockpit-owned ROBA capability."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        runtime: Api,
        workbench: Api,
        loom: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.runtime = runtime
        self.workbench = workbench
        self.loom = loom

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(
            prog="dix-cockpit-master-workbench",
            description="Open the live private Cockpit ROBA in the generic Loom workbench.",
        )
        parser.add_argument("--session", default="dix")
        parser.add_argument("--logo", choices=("dix", "roba"), default="dix")
        try:
            arguments = parser.parse_args(list(argv))
        except SystemExit as exc:
            return int(exc.code)

        secret = ""
        try:
            environment = self.runtime.require("owner_environment")(
                session=arguments.session
            )
            if not _string_mapping(environment):
                raise TypeError("Cockpit owner environment must be a string mapping")
            secret = _required_string(environment, "ROBA_CONTROL_TOKEN")
            seed = self._seed(arguments.session, environment, secret)
            result = self.workbench.require("start")(
                self.loom.require("execute"),
                seed,
                arguments.logo,
                True,
                show_branding=False,
            )
            if type(result) is not int:
                raise TypeError("Cockpit master workbench must return an integer exit code")
            return result
        except Exception as exc:  # noqa: BLE001 - explicit secret-redacting CLI boundary
            detail = str(exc)
            if secret:
                detail = detail.replace(secret, "[redacted]")
            print(
                f"cockpit master workbench error: {type(exc).__name__}: {detail}",
                file=sys.stderr,
            )
            return 2

    def _seed(
        self,
        session: str,
        environment: Mapping[str, str],
        control_token: str,
    ) -> dict[str, object]:
        daemon_locator = _required_string(environment, "ROBA_DAEMON")
        if daemon_locator != "id:default":
            raise RuntimeError("Cockpit owner runtime has an unexpected daemon locator")
        status = self.runtime.require("status")(session=session)
        paths = self.runtime.require("paths")(session=session)
        if not isinstance(status, Mapping):
            raise TypeError("Cockpit runtime status must be a mapping")
        if not _string_mapping(paths):
            raise TypeError("Cockpit runtime paths must be a string mapping")
        if status.get("state") != "running" or status.get("owned") is not True:
            raise RuntimeError("Cockpit owner runtime is not healthy")
        pid = status.get("pid")
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise RuntimeError("Cockpit owner runtime has an invalid process identity")
        return {
            "daemon_id": "default",
            "runtime_root": _required_string(environment, "ROBA_RUNTIME_ROOT"),
            "logs_root": _required_string(environment, "ROBA_LOGS_ROOT"),
            "timeout": _timeout(self.config.get("timeout", 5.0)),
            "pid": pid,
            "daemon_socket": _required_string(paths, "daemon_socket"),
            "control_socket": _required_string(paths, "control_socket"),
            "control_token": control_token,
        }


def _string_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _required_string(value: Mapping[str, str], field: str) -> str:
    item = value.get(field)
    if not isinstance(item, str) or not item:
        raise RuntimeError(f"Cockpit owner runtime is missing {field}")
    return item


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        raise TypeError("Cockpit workbench timeout must be a positive number")
    return float(value)
