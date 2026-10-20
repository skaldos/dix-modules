from __future__ import annotations

import copy
import math
import tomllib
from collections.abc import Callable, Mapping, Sequence

type ValuePath = tuple[str | int, ...]


class ValuePathError(ValueError):
    """A path does not identify a value in the current draft."""


class ValueOperationError(ValueError):
    """A local structural operation is invalid for the selected value."""


class ValueDraft:
    """One detached mutable value plus a session-local deep-copy register."""

    def __init__(self, value: object) -> None:
        self.value = copy.deepcopy(value)
        self._original = copy.deepcopy(self.value)
        self._register: object = None
        self._has_register = False

    @property
    def dirty(self) -> bool:
        return not semantically_equal(self.value, self._original)

    @property
    def has_register(self) -> bool:
        return self._has_register

    def at(self, path: Sequence[str | int] = ()) -> object:
        """Return a detached copy of the value at one explicit path."""
        return copy.deepcopy(_resolve(self.value, _path(path)))

    def replace(self, path: Sequence[str | int], value: object) -> None:
        replacement = copy.deepcopy(value)

        def mutate(candidate: object) -> object:
            parts = _path(path)
            if not parts:
                return replacement
            parent = _resolve(candidate, parts[:-1])
            _replace_child(parent, parts[-1], replacement)
            return candidate

        self._mutate(mutate)

    def add_mapping(self, path: Sequence[str | int], key: str, value: object) -> None:
        valid_key = _mapping_key(key)
        replacement = copy.deepcopy(value)

        def mutate(candidate: object) -> object:
            mapping = _mapping(_resolve(candidate, _path(path)))
            if valid_key in mapping:
                raise ValueOperationError(f"mapping key already exists: {valid_key!r}")
            mapping[valid_key] = replacement
            return candidate

        self._mutate(mutate)

    def rename_mapping(
        self,
        path: Sequence[str | int],
        old_key: str,
        new_key: str,
    ) -> None:
        old = _mapping_key(old_key)
        new = _mapping_key(new_key)

        def mutate(candidate: object) -> object:
            mapping = _mapping(_resolve(candidate, _path(path)))
            if old not in mapping:
                raise ValueOperationError(f"mapping key does not exist: {old!r}")
            if new != old and new in mapping:
                raise ValueOperationError(f"mapping key already exists: {new!r}")
            if new == old:
                return candidate
            items = [(new if key == old else key, item) for key, item in mapping.items()]
            mapping.clear()
            mapping.update(items)
            return candidate

        self._mutate(mutate)

    def delete_mapping(self, path: Sequence[str | int], key: str) -> None:
        valid_key = _mapping_key(key)

        def mutate(candidate: object) -> object:
            mapping = _mapping(_resolve(candidate, _path(path)))
            if valid_key not in mapping:
                raise ValueOperationError(f"mapping key does not exist: {valid_key!r}")
            del mapping[valid_key]
            return candidate

        self._mutate(mutate)

    def insert_list(self, path: Sequence[str | int], index: int, value: object) -> None:
        replacement = copy.deepcopy(value)

        def mutate(candidate: object) -> object:
            sequence = _list(_resolve(candidate, _path(path)))
            valid_index = _insert_index(index, len(sequence))
            sequence.insert(valid_index, replacement)
            return candidate

        self._mutate(mutate)

    def append_list(self, path: Sequence[str | int], value: object) -> None:
        replacement = copy.deepcopy(value)

        def mutate(candidate: object) -> object:
            _list(_resolve(candidate, _path(path))).append(replacement)
            return candidate

        self._mutate(mutate)

    def delete_list(self, path: Sequence[str | int], index: int) -> None:
        def mutate(candidate: object) -> object:
            sequence = _list(_resolve(candidate, _path(path)))
            del sequence[_existing_index(index, len(sequence))]
            return candidate

        self._mutate(mutate)

    def copy_to_register(self, path: Sequence[str | int]) -> None:
        copied = copy.deepcopy(_resolve(self.value, _path(path)))
        self._register = copied
        self._has_register = True

    def register_value(self) -> object:
        if not self._has_register:
            raise ValueOperationError("local value register is empty")
        return copy.deepcopy(self._register)

    def put_replacement(self, path: Sequence[str | int]) -> None:
        self.replace(path, self.register_value())

    def put_mapping(self, path: Sequence[str | int], key: str) -> None:
        self.add_mapping(path, key, self.register_value())

    def put_list(self, path: Sequence[str | int], index: int | None = None) -> None:
        if index is None:
            self.append_list(path, self.register_value())
        else:
            self.insert_list(path, index, self.register_value())

    def _mutate(self, operation: Callable[[object], object]) -> None:
        candidate = copy.deepcopy(self.value)
        result = operation(candidate)
        self.value = result


def parse_toml_literal(raw: str) -> object:
    """Parse exactly one TOML value without a Python-eval fallback."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("TOML literal must not be empty")
    try:
        parsed = tomllib.loads(f"__value__ = {raw}\n")
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        raise ValueError(f"invalid TOML literal: {exc}") from None
    if set(parsed) != {"__value__"}:
        raise ValueError("input must contain exactly one TOML literal")
    return copy.deepcopy(parsed["__value__"])


def semantically_equal(left: object, right: object) -> bool:
    """Compare supported native values while treating corresponding NaNs as equal."""
    if isinstance(left, float) and isinstance(right, float):
        return (math.isnan(left) and math.isnan(right)) or left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, Mapping):
        return set(left) == set(right) and all(
            semantically_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            semantically_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    try:
        return bool(left == right)
    except Exception:  # noqa: BLE001 - unknown local values are conservatively dirty
        return False


def _path(path: Sequence[str | int]) -> ValuePath:
    if isinstance(path, (str, bytes, bytearray)) or not isinstance(path, Sequence):
        raise TypeError("value path must be a sequence of mapping keys and list indices")
    parts = tuple(path)
    for part in parts:
        if not isinstance(part, str) and type(part) is not int:
            raise TypeError("value path parts must be strings or integers")
    return parts


def _resolve(value: object, path: ValuePath) -> object:
    current = value
    for part in path:
        if isinstance(current, dict) and isinstance(part, str):
            if part not in current:
                raise ValuePathError(f"mapping path part does not exist: {part!r}")
            current = current[part]
            continue
        if isinstance(current, list) and type(part) is int:
            current = current[_existing_index(part, len(current))]
            continue
        raise ValuePathError("path does not match the current mapping/list structure")
    return current


def _replace_child(parent: object, part: str | int, value: object) -> None:
    if isinstance(parent, dict) and isinstance(part, str):
        if part not in parent:
            raise ValuePathError(f"mapping path part does not exist: {part!r}")
        parent[part] = value
        return
    if isinstance(parent, list) and type(part) is int:
        parent[_existing_index(part, len(parent))] = value
        return
    raise ValuePathError("replacement path does not match a mapping/list child")


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueOperationError("selected value is not a string-keyed mapping")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueOperationError("selected value is not a list")
    return value


def _mapping_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip() or "\x00" in key:
        raise ValueOperationError("mapping key must be a non-blank string without NUL")
    return key


def _existing_index(index: int, length: int) -> int:
    if type(index) is not int or not 0 <= index < length:
        raise ValueOperationError(f"list index is outside 0..{max(length - 1, 0)}")
    return index


def _insert_index(index: int, length: int) -> int:
    if type(index) is not int or not 0 <= index <= length:
        raise ValueOperationError(f"list insertion index is outside 0..{length}")
    return index
