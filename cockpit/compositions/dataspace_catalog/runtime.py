from __future__ import annotations

import copy
import fcntl
import os
import re
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path

from roba import ResourceNotFound, RobaClient

# Separate owned Context and key: never read, migrate, or initialize the Store catalog.
_CONTEXT, _SOCKET, _KEY = 'd', 'd', 'dataspaces'


def _name(value, label):
    if (type(value) is not str or not value.strip()
            or any(ord(c) < 32 or c in '\x7f\x85\u2028\u2029' for c in value)):
        raise ValueError(label + ' must be a non-empty single-line name')
    return value


class Runtime:
    """Volatile, session-owned materialization definitions, not live handles or Stores."""

    def __init__(self, *, context, config, runtime, contexts, materializers):
        if config:
            raise ValueError('Dataspace catalog has no target configuration')
        self.runtime, self.contexts, self.materializers = runtime, contexts, materializers

    def register_materializer(self, materializer_id: str, materializer: object) -> None:
        self.materializers.require('register')(materializer_id, materializer)

    def materializers_list(self) -> list[str]:
        return self.materializers.require('list')()

    def draft(self, materializer_id: str) -> dict[str, object]:
        return {'dataspace_id': '', 'materializer': materializer_id,
                'configuration': self.materializers.require('draft')(materializer_id)}

    def validate_configuration(self, materializer_id: str, value: object) -> dict[str, object]:
        return self.materializers.require('validate')(materializer_id, value)

    def _shape(self, value):
        if not isinstance(value, Mapping) or set(value) != {'dataspace_id', 'materializer', 'configuration'}:
            raise ValueError('Dataspace requires exactly dataspace_id, materializer and configuration')
        _name(value['dataspace_id'], 'Dataspace ID')
        _name(value['materializer'], 'materializer ID')
        # Native data shape only: reads do not invoke any domain materializer.
        self.materializers.require('native_configuration')(value['configuration'])
        return value

    def _entry(self, value):
        value = self._shape(value)
        canonical = self.validate_configuration(value['materializer'], value['configuration'])
        return {'dataspace_id': value['dataspace_id'], 'materializer': value['materializer'],
                'configuration': canonical}

    def _record(self, value, ident):
        try:
            if (type(value) is not dict or set(value) != {'definition', 'revision'}
                    or type(value['revision']) is not str
                    or not re.fullmatch('[0-9a-f]{32}', value['revision'])):
                raise ValueError
            definition = self._shape(value['definition'])
            if definition['dataspace_id'] != ident:
                raise ValueError
        except (ValueError, TypeError, KeyError, RecursionError):
            raise RuntimeError('private Dataspace record has an invalid shape') from None
        return copy.deepcopy(value)

    def list(self, session: str = 'dix') -> list[dict[str, object]]:
        with self._catalog(session) as client:
            values = client.get(_KEY)
            return [self._record(values[key], key)['definition'] for key in sorted(values)]

    def get(self, dataspace_id: str, session: str = 'dix') -> dict[str, object]:
        return self.record(dataspace_id, session)['definition']

    def record(self, dataspace_id: str, session: str = 'dix') -> dict[str, object]:
        _name(dataspace_id, 'Dataspace ID')
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if dataspace_id not in values:
                raise ValueError('Dataspace does not exist; reload the catalog')
            return self._record(values[dataspace_id], dataspace_id)

    def create(self, value: object, session: str = 'dix') -> None:
        entry = self._entry(value)
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if entry['dataspace_id'] in values:
                raise ValueError('Dataspace ID already exists')
            values[entry['dataspace_id']] = {'definition': entry, 'revision': uuid.uuid4().hex}
            client.set(_KEY, values)

    def update(self, dataspace_id: str, value: object, session: str = 'dix') -> None:
        _name(dataspace_id, 'Dataspace ID')
        entry = self._entry(value)
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if dataspace_id not in values:
                raise ValueError('Dataspace does not exist; reload the catalog')
            self._record(values[dataspace_id], dataspace_id)
            if entry['dataspace_id'] != dataspace_id and entry['dataspace_id'] in values:
                raise ValueError('Dataspace ID already exists')
            del values[dataspace_id]
            values[entry['dataspace_id']] = {'definition': entry, 'revision': uuid.uuid4().hex}
            client.set(_KEY, values)

    def remove(self, dataspace_id: str, session: str = 'dix') -> None:
        _name(dataspace_id, 'Dataspace ID')
        with self._catalog(session) as client:
            values = client.get(_KEY)
            if dataspace_id not in values:
                raise ValueError('Dataspace does not exist; reload the catalog')
            self._record(values[dataspace_id], dataspace_id)
            del values[dataspace_id]
            client.set(_KEY, values)

    @contextmanager
    def _catalog(self, session):
        env = self.runtime.require('owner_environment')(session=session)
        paths = self.runtime.require('paths')(session=session)
        lock = Path(paths['session_runtime_root']) / 'dataspaces.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            socket = (Path(paths['roba_runtime_root']) / 'daemons/default/contexts'
                      / _CONTEXT / 'sockets' / f'{_SOCKET}.sock')
            client = RobaClient(env={}, timeout=5.0).context(locator=f'unix:{socket}', token=None)
            existing = self.contexts.require('native_list')(
                control_locator=env['ROBA_CONTROL'], control_token=env['ROBA_CONTROL_TOKEN'],
                environment=env)
            if not any(item['id'] == _CONTEXT for item in existing):
                created = self.contexts.require('native_create')(
                    control_locator=env['ROBA_CONTROL'], control_token=env['ROBA_CONTROL_TOKEN'],
                    context_id=_CONTEXT, name='Cockpit volatile Dataspace catalog', environment=env)
                owner = RobaClient(env={}).context(
                    locator=f"unix:{created['socket']}", token=created['owner_token'])
                try:
                    owner.set(_KEY, {})
                    owner.socket_create(socket_id=_SOCKET, read=['context'], write=['context'])
                except Exception:
                    self.contexts.require('native_delete')(
                        control_locator=env['ROBA_CONTROL'],
                        control_token=env['ROBA_CONTROL_TOKEN'], context_id=_CONTEXT,
                        environment=env)
                    raise
            try:
                value = client.get(_KEY)
            except ResourceNotFound:
                raise RuntimeError('private Dataspace catalog is incomplete') from None
            if type(value) is not dict:
                raise RuntimeError('private Dataspace catalog has an invalid shape')
            # Check every stored shape before any mutation, never silently preserve/repair garbage.
            for ident, record in value.items():
                self._record(record, ident)
            yield client
        finally:
            os.close(fd)
