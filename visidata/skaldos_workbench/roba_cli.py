"""Explicit one-key DIX-ROBA CLI access; no shell or ambient credential path."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class AccessError(RuntimeError):
    """A bound get/set failed without exposing backend values or credentials."""


@dataclass(frozen=True)
class RobaCliAccess:
    """Bind a known CLI binary to one capability socket and one context key."""

    executable: Path
    locator: str
    key: str
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if not self.executable.is_file():
            raise ValueError("dix-roba-cli executable is not a file")
        if not self.locator.startswith("unix:/"):
            raise ValueError("a tokenless absolute unix: capability locator is required")
        if not self.key.strip():
            raise ValueError("key must not be empty")

    def get_key(self) -> object:
        result = self._call("get")
        try:
            return json.loads(result, parse_constant=_reject_constant)
        except ValueError:
            raise AccessError("dix-roba-cli data get did not return JSON") from None

    def set_key(self, value: object) -> None:
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ValueError("draft is not a finite JSON value") from None
        self._call("set", encoded)

    def _call(self, method: str, encoded: str | None = None) -> str:
        argv = [
            str(self.executable), "data", method,
            "--locator", self.locator, "--key", self.key,
        ]
        if encoded is not None:
            argv.extend(("--value_json", encoded))
        try:
            result = subprocess.run(
                argv, capture_output=True, text=True, check=False, timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            # TimeoutExpired can retain argv, including --value_json, in its traceback.
            raise AccessError(f"dix-roba-cli data {method} could not complete") from None
        if result.returncode:
            # The CLI may include the submitted value or backend details in stderr.
            raise AccessError(
                f"dix-roba-cli data {method} failed (exit {result.returncode})"
            )
        return result.stdout.strip()


def _reject_constant(_value: str) -> object:
    raise ValueError("non-finite number is not JSON")
