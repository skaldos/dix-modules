from __future__ import annotations
from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from dix.core.composition import CompositionRuntimeContext

class Runtime:
    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object]) -> None:
        self.context, self.config = context, config
        raw = config.get("path", os.environ.get("SKALDOS_SWAY_ACTIVE_MEMBERS_FILE"))
        if not isinstance(raw, str) or not raw:
            raise ValueError("active members path requires path or SKALDOS_SWAY_ACTIVE_MEMBERS_FILE")
        self.path = Path(raw)

    def get(self) -> list[int]:
        if not self.path.exists():
            return []
        payload = self.path.read_bytes()
        if payload == b"\n":
            return []
        if payload.count(b"\n") != 1 or not payload.endswith(b"\n"):
            raise ValueError("active members must be exactly one newline-terminated line")
        try:
            tokens = payload[:-1].decode("ascii").split(" ")
        except UnicodeDecodeError as exc:
            raise ValueError("active members must be ASCII") from exc
        if any(not _canonical(token) for token in tokens):
            raise ValueError("active members contain a non-canonical con_id")
        result = [int(token) for token in tokens]
        _validate(result)
        return result

    def set(self, members: list[int]) -> None:
        values = _validate(members)
        _atomic(self.path, (" ".join(map(str, values)) + "\n").encode("ascii"))

def _canonical(value: str) -> bool:
    return bool(value) and value[0] in "123456789" and value.isascii() and value.isdigit()

def _validate(value: object) -> list[int]:
    if not isinstance(value, list) or any(type(v) is not int or v <= 0 for v in value):
        raise TypeError("active members must be a list of positive integer con_ids")
    if len(set(value)) != len(value):
        raise ValueError("active members must not contain duplicates")
    return list(value)

def _atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.name}.", delete=False) as out:
            temporary = out.name; out.write(payload); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, path); temporary = None
    finally:
        if temporary: Path(temporary).unlink(missing_ok=True)
