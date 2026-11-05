from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from contextlib import nullcontext


class DataspaceSession:
    """Only the four-method handle and an external revision barrier; no provider knowledge."""

    def __init__(self, space, *, guard=None, title='Dataspace'):
        for name in ('describe', 'get', 'set', 'delete'):
            if not callable(getattr(space, name, None)):
                raise TypeError('Dataspace requires describe, get, set and delete')
        self.space, self.guard, self.title = space, guard or nullcontext, title
        self.description = None
        self.path = ()
        self.cache = {}
        self.error = self.notice = ''

    def reload(self):
        try:
            with self.guard():
                description = self._description(self.space.describe())
        except Exception as exc:  # noqa: BLE001 - never expose target/configuration through errors
            self.failure('Describe', exc)
            return False
        self.description = description
        self.cache.clear()
        if len(self.path) == 2 and self.path[1] not in description['sets']:
            self.path = ()
        self.error = self.notice = ''
        return True

    @staticmethod
    def _description(value):
        if (not isinstance(value, Mapping) or type(value.get('id')) is not str
                or not isinstance(value.get('sets'), Mapping)):
            raise TypeError('invalid Dataspace description')
        sets = {}
        for role, dataset in value['sets'].items():
            if type(role) is not str or not isinstance(dataset, Mapping):
                raise TypeError('invalid Dataspace set')
            if type(dataset.get('id')) is not str or not isinstance(dataset.get('fields'), Mapping):
                raise TypeError('invalid Dataset description')
            fields = {}
            for field, spec in dataset['fields'].items():
                if (type(field) is not str or not isinstance(spec, Mapping)
                        or type(spec.get('contract')) is not str
                        or type(spec.get('has_default')) is not bool):
                    raise TypeError('invalid Field description')
                operations = spec.get('operations')
                effective = spec.get('effective_operations', operations)
                for offered in (operations, effective):
                    if (type(offered) is not list or any(type(op) is not str for op in offered)
                            or len(set(offered)) != len(offered)
                            or not set(offered) <= {'get', 'set', 'delete'}):
                        raise TypeError('invalid Field operations')
                if not set(effective) <= set(operations):
                    raise TypeError('effective operations cannot expand Field operations')
                fields[field] = {'contract': spec['contract'], 'has_default': spec['has_default'],
                                 'operations': list(operations), 'effective_operations': list(effective)}
            sets[role] = {'id': dataset['id'], 'mounted': dataset.get('mounted') is True,
                          'fields': fields}
        return {'id': value['id'], 'sets': sets}

    @property
    def breadcrumb(self):
        return self.title + (' / ' + ' / '.join(self.path) if self.path else '')

    def rows(self):
        if self.description is None:
            return []
        if not self.path:
            return [{'key': self.description['id'], 'kind': 'layout'}]
        if len(self.path) == 1:
            return [{'key': role, 'kind': 'set', 'dataset': spec['id']}
                    for role, spec in self.description['sets'].items()]
        role = self.path[1]
        rows = []
        for field, spec in self.description['sets'][role]['fields'].items():
            loaded = (role, field) in self.cache
            row = {'key': field, 'kind': 'field', 'set': role, **copy.deepcopy(spec), 'loaded': loaded}
            if loaded:
                row['value'] = copy.deepcopy(self.cache[(role, field)])
            rows.append(row)
        return rows

    def enter(self, key):
        if self.description is None:
            raise ValueError('Describe must succeed before navigation')
        if not self.path and key == self.description['id']:
            self.path = (key,)
        elif len(self.path) == 1 and key in self.description['sets']:
            self.path += (key,)
        else:
            raise ValueError('Only a declared Layout or Set can be entered')
        self.error = self.notice = ''

    def parent(self):
        self.path = self.path[:-1]
        self.error = self.notice = ''

    def _field(self, role, field, operation):
        if self.description is None or role not in self.description['sets']:
            raise KeyError('Unknown Dataspace set')
        fields = self.description['sets'][role]['fields']
        if field not in fields:
            raise KeyError('Unknown Dataspace field')
        spec = fields[field]
        if operation not in spec['operations'] or operation not in spec['effective_operations']:
            raise PermissionError('Field does not offer ' + operation)
        return spec

    def load(self, role, field):
        try:
            self._field(role, field, 'get')
            with self.guard():
                value = self.space.get(role, field)
            kind_of(value)
        except Exception as exc:  # noqa: BLE001 - preserve cache, never display opaque exception repr
            self.failure('Get', exc)
            return False
        self.cache[(role, field)] = copy.deepcopy(value)
        self.error, self.notice = '', 'Value loaded; a default is not proof of storage'
        return True

    def set_value(self, role, field, value):
        try:
            self._field(role, field, 'set')
            with self.guard():
                canonical = self.space.set(role, field, copy.deepcopy(value))
            kind_of(canonical)
        except Exception as exc:  # noqa: BLE001 - a post-write error never implies rollback
            self.failure('Set', exc)
            self.notice = 'Set failed; target may have changed. Inspect the raw Store.'
            return False
        self.cache[(role, field)] = copy.deepcopy(canonical)
        self.error, self.notice = '', 'Complete Field value saved'
        return True

    def delete_value(self, role, field):
        try:
            self._field(role, field, 'delete')
            with self.guard():
                self.space.delete(role, field)
        except Exception as exc:  # noqa: BLE001 - no invented success or rollback
            self.failure('Delete', exc)
            return False
        self.cache.pop((role, field), None)
        self.error, self.notice = '', 'Stored Field deleted; a later Get may return a default'
        return True

    def failure(self, stage, error):
        self.error = stage + ' failed: ' + type(error).__name__
        self.notice = ''


def kind_of(value):
    kind = {str: 'string', int: 'integer', float: 'number', bool: 'boolean',
            type(None): 'null', list: 'array', dict: 'object'}.get(type(value))
    if kind is None or (type(value) is float and not math.isfinite(value)):
        raise TypeError('the value editor supports finite native consumer values')
    return kind
