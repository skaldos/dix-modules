from __future__ import annotations

import copy
import inspect
import math


def _name(value, label):
    if (type(value) is not str or not value.strip()
            or any(ord(c) < 32 or c in '\x7f\x85\u2028\u2029' for c in value)):
        raise ValueError(label + ' must be a non-empty single-line name')
    return value


def configuration(value):
    """Detach only finite native configuration, never live objects or implicit coercions."""
    def visit(item, active):
        kind = type(item)
        if item is None or kind in (str, bool, int):
            return
        if kind is float and math.isfinite(item):
            return
        if kind not in (list, dict) or id(item) in active:
            raise ValueError('configuration must contain finite native data')
        active.add(id(item))
        try:
            if kind is dict and any(type(key) is not str for key in item):
                raise ValueError('configuration requires string object keys')
            for child in item.values() if kind is dict else item:
                visit(child, active)
        finally:
            active.remove(id(item))
    if type(value) is not dict:
        raise ValueError('configuration must be a native object')
    try:
        visit(value, set())
    except RecursionError:
        raise ValueError('configuration nesting is too deep') from None
    return copy.deepcopy(value)


class Runtime:
    """Only capabilities supplied by the static owning app; never code lookup from data."""

    def __init__(self, *, context, config):
        if config:
            raise ValueError('materializer bindings come from explicit app dependencies')
        self._bindings = {}

    def register(self, materializer_id: str, materializer: object) -> None:
        _name(materializer_id, 'materializer ID')
        if materializer_id in self._bindings:
            raise ValueError('materializer is already registered in this graph')
        try:
            functions = {name: materializer.require(name)
                         for name in ('draft', 'validate', 'materialize')}
        except Exception:  # noqa: BLE001 - validate a private exposed capability, never echo it
            raise ValueError('materializer requires draft, validate and materialize') from None
        if any(not callable(fn) or inspect.iscoroutinefunction(fn) for fn in functions.values()):
            raise ValueError('materializer requires three synchronous exposed functions')
        self._bindings[materializer_id] = functions

    def list(self) -> list[str]:
        return sorted(self._bindings)

    def _bound(self, materializer_id):
        _name(materializer_id, 'materializer ID')
        if materializer_id not in self._bindings:
            raise ValueError('unknown local materializer')
        return self._bindings[materializer_id]

    def native_configuration(self, value: object) -> dict[str, object]:
        return configuration(value)

    def draft(self, materializer_id: str) -> dict[str, object]:
        function = self._bound(materializer_id)['draft']
        try:
            return configuration(function())
        except Exception as exc:  # noqa: BLE001 - private configuration/target redaction boundary
            raise ValueError('Materializer draft failed: ' + type(exc).__name__) from None

    def validate(self, materializer_id: str, value: object) -> dict[str, object]:
        function = self._bound(materializer_id)['validate']
        value = configuration(value)
        try:
            return configuration(function(value))
        except Exception as exc:  # noqa: BLE001 - private configuration/target redaction boundary
            raise ValueError('Materializer configuration is invalid: ' + type(exc).__name__) from None

    def materialize(self, materializer_id: str, value: object) -> object:
        function = self._bound(materializer_id)['materialize']
        value = self.validate(materializer_id, value)
        try:
            lease = function(value)
        except Exception as exc:  # noqa: BLE001 - private configuration/target redaction boundary
            raise RuntimeError('Dataspace materialization failed: ' + type(exc).__name__) from None
        try:
            if (not callable(getattr(lease, 'close', None))
                    or any(not callable(getattr(lease.space, name, None))
                           for name in ('describe', 'get', 'set', 'delete'))):
                raise TypeError
        except Exception:  # noqa: BLE001 - validate a private exposed capability, never echo it
            if callable(getattr(lease, 'close', None)):
                try:
                    lease.close()
                except Exception as exc:  # noqa: BLE001 - private ownership cleanup boundary  # noqa: BLE001 - private configuration/target redaction boundary
                    raise RuntimeError('Materializer cleanup failed: ' + type(exc).__name__) from None
            raise TypeError('materializer must return an owned space/close lifecycle') from None
        return lease
