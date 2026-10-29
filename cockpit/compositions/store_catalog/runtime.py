from __future__ import annotations

import copy
import fcntl
import os
import re
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from dix.core.composition import CompositionRuntimeContext
from roba import ResourceNotFound, RobaClient

# Private to the owned daemon. Never a registered external Store.
_CONTEXT = "c"
_SOCKET = "c"
_KEY = "stores"


class Runtime:
    """Volatile catalog; all multi-call changes are serialized per owned session."""

    def __init__(self, *, context: CompositionRuntimeContext, config: Mapping[str, object],
                 runtime, contexts, providers) -> None:
        self.runtime = runtime
        self.contexts = contexts
        self.providers = providers

    def register_provider(self, provider_id: str, provider: object) -> None:
        self.providers.require("register")(provider_id, provider)

    def providers_list(self) -> list[str]:
        return self.providers.require("list")()

    def draft(self, provider_id: str) -> dict[str, object]:
        return {"store_id": "", "provider": provider_id,
                "connection": self.providers.require("call")(provider_id, "draft")}

    def provider_call(self, provider_id: str, operation: str, *args: object) -> object:
        return self.providers.require("call")(provider_id, operation, *args)

    def list(self, session: str = "dix") -> list[dict[str, object]]:
        with self._catalog(session) as client:
            values = client.get(_KEY)
            return [self._record(values[key])["definition"] for key in sorted(values)]

    def get(self, store_id: str, session: str = "dix") -> dict[str, object]:
        return self.record(store_id, session)["definition"]

    def record(self, store_id: str, session: str = "dix") -> dict[str, object]:
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if store_id not in values:
                raise ValueError("store does not exist; reload the catalog")
            return self._record(values[store_id])

    @staticmethod
    def _record(value):
        # Private volatile format; no migration or silent repair of an old/malformed catalog.
        if (not isinstance(value, dict) or set(value) != {"definition", "revision"}
                or not isinstance(value["definition"], dict)
                or set(value["definition"]) != {"store_id", "provider", "connection"}
                or not isinstance(value["revision"], str)
                or not re.fullmatch(r"[0-9a-f]{32}", value["revision"])):
            raise RuntimeError("private Store record has an invalid shape")
        return copy.deepcopy(value)

    def create(self, value: object, session: str = "dix") -> None:
        entry = self._entry(value)
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if entry["store_id"] in values:
                raise ValueError("store ID already exists")
            values[entry["store_id"]] = {"definition": entry, "revision": uuid.uuid4().hex}
            client.set(_KEY, values)

    def update(self, store_id: str, value: object, session: str = "dix") -> None:
        entry = self._entry(value)
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if store_id not in values:
                raise ValueError("store does not exist; reload the catalog")
            if entry["store_id"] != store_id and entry["store_id"] in values:
                raise ValueError("store ID already exists")
            del values[store_id]
            values[entry["store_id"]] = {"definition": entry, "revision": uuid.uuid4().hex}
            client.set(_KEY, values)

    def remove(self, store_id: str, session: str = "dix") -> None:
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if store_id not in values:
                raise ValueError("store does not exist; reload the catalog")
            del values[store_id]
            client.set(_KEY, values)

    def _entry(self, value: object) -> dict[str, object]:
        if not isinstance(value, Mapping) or set(value) != {"store_id", "provider", "connection"}:
            raise ValueError("store requires exactly store_id, provider and connection")
        store_id = value["store_id"]
        if (not isinstance(store_id, str) or not store_id.strip()
                or any(ord(c) < 32 for c in store_id)):
            raise ValueError("store ID must be a non-empty single-line name")
        provider = value["provider"]
        if not isinstance(provider, str):
            raise TypeError("provider ID must be a string")
        connection = self.provider_call(provider, "validate", value["connection"])
        return {"store_id": store_id, "provider": provider, "connection": connection}

    @contextmanager
    def _catalog(self, session: str):
        # Validate live ownership before touching any runtime file or native Context.
        env = self.runtime.require("owner_environment")(session=session)
        paths = self.runtime.require("paths")(session=session)
        lock = Path(paths["session_runtime_root"]) / "stores.lock"
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            socket = (Path(paths["roba_runtime_root"]) / "daemons/default/contexts"
                      / _CONTEXT / "sockets" / f"{_SOCKET}.sock")
            client = RobaClient(env={}, timeout=5.0).context(locator=f"unix:{socket}", token=None)
            existing = self.contexts.require("native_list")(
                control_locator=env["ROBA_CONTROL"], control_token=env["ROBA_CONTROL_TOKEN"],
                environment=env)
            if not any(item["id"] == _CONTEXT for item in existing):
                created = self.contexts.require("native_create")(
                    control_locator=env["ROBA_CONTROL"], control_token=env["ROBA_CONTROL_TOKEN"],
                    context_id=_CONTEXT, name="Cockpit volatile Store catalog", environment=env)
                owner = RobaClient(env={}).context(
                    locator=f"unix:{created['socket']}", token=created["owner_token"])
                try:
                    owner.set(_KEY, {})
                    owner.socket_create(socket_id=_SOCKET, read=["context"], write=["context"])
                except Exception:
                    self.contexts.require("native_delete")(
                        control_locator=env["ROBA_CONTROL"],
                        control_token=env["ROBA_CONTROL_TOKEN"], context_id=_CONTEXT,
                        environment=env)
                    raise
            # No repair of a pre-existing malformed scope. Fail closed instead.
            try:
                value = client.get(_KEY)
            except ResourceNotFound:
                raise RuntimeError("private Store catalog is incomplete") from None
            if not isinstance(value, dict):
                raise TypeError("private Store catalog has an invalid shape")
            yield client
        finally:
            os.close(fd)
