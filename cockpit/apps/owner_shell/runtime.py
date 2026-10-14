from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dix.core.application import ApplicationRuntimeContext


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    """Load the private owner artifact only in the shell child process."""

    def __init__(
        self,
        *,
        context: ApplicationRuntimeContext,
        config: Mapping[str, object],
        runtime: Api,
    ) -> None:
        self.context = context
        self.config = config
        self.runtime = runtime

    def main(self, argv: Sequence[str]) -> int:
        parser = argparse.ArgumentParser(prog="dix-cockpit-shell")
        parser.add_argument("--session", default="dix")
        try:
            arguments = parser.parse_args(list(argv))
            environment = self._environment(arguments.session)
            shell = shutil.which("zsh", path=environment.get("PATH"))
            if shell is None:
                raise RuntimeError("zsh is required for the Cockpit owner shell")
            os.execvpe(shell, [shell, "-d", "-i"], environment)
        except SystemExit as exc:
            return int(exc.code)
        except Exception as exc:  # noqa: BLE001 - CLI boundary must preserve the concrete error
            print(f"cockpit owner shell error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        return 0

    def _environment(self, session: str) -> dict[str, str]:
        owner = self.runtime.require("owner_environment")(session=session)
        paths = self.runtime.require("paths")(session=session)
        if not _strings(owner) or not _strings(paths):
            raise TypeError("Cockpit owner environment and paths must be string mappings")

        zsh_root = Path(paths["zsh_root"])
        zsh_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        zsh_root.chmod(0o700)
        source = (
            Path(
                os.environ.get(
                    "DIX_COCKPIT_ZSH_CONFIG",
                    str(Path(__file__).parents[2] / "integrations" / "zsh" / ".zshrc"),
                )
            )
            .expanduser()
            .resolve(strict=False)
        )
        if not source.is_file():
            raise RuntimeError(f"Cockpit Zsh config does not exist: {source}")
        target = zsh_root / ".zshrc"
        target.write_bytes(source.read_bytes())
        target.chmod(0o600)
        history = Path(paths["history_file"])
        history.touch(mode=0o600, exist_ok=True)
        history.chmod(0o600)

        environment = dict(os.environ)
        environment.update(owner)
        environment.update(
            {
                "ZDOTDIR": str(zsh_root),
                "HISTFILE": str(history),
                "DIX_COCKPIT_OWNER_SHELL": "1",
            }
        )
        return environment


def _strings(value: object) -> bool:
    return isinstance(value, Mapping) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )
