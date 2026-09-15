from __future__ import annotations
from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from dix.core.composition import CompositionRuntimeContext

_TARGETS = frozenset({"basic", "group"})
class Runtime:
    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config
        raw = config.get("path", os.environ.get("SKALDOS_SWAY_NAVIGATION_TARGET_FILE"))
        if not isinstance(raw, str) or not raw:
            raise ValueError("navigation target path requires path or SKALDOS_SWAY_NAVIGATION_TARGET_FILE")
        self.path = Path(raw)
    def get(self) -> str:
        if not self.path.exists(): return "basic"
        payload = self.path.read_bytes()
        if payload not in {b"basic\n", b"group\n"}:
            raise ValueError("navigation target must be exactly basic\\n or group\\n")
        return payload[:-1].decode("ascii")
    def set(self, target: str) -> None:
        if target not in _TARGETS: raise ValueError(f"unsupported navigation target: {target!r}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=self.path.parent, prefix=f".{self.path.name}.", delete=False) as out:
                temporary=out.name; out.write(f"{target}\n".encode()); out.flush(); os.fsync(out.fileno())
            os.replace(temporary, self.path); temporary=None
        finally:
            if temporary: Path(temporary).unlink(missing_ok=True)
