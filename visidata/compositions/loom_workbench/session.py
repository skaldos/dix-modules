from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass


class LoomReferenceError(ValueError):
    """A provider result violates the closed ObjectReference contract."""


class LoomResultError(TypeError):
    """A provider result is not an ordered sequence of references."""


@dataclass(frozen=True)
class ObjectReference:
    object_id: str
    description: str
    value: object


@dataclass
class LoomDraft:
    """A detached local copy of one complete ObjectReference value."""

    reference: ObjectReference
    value: object
    _original: object

    @classmethod
    def from_reference(cls, reference: ObjectReference) -> LoomDraft:
        value = copy.deepcopy(reference.value)
        return cls(reference=reference, value=value, _original=copy.deepcopy(value))

    @property
    def dirty(self) -> bool:
        return self.value != self._original

    def at(self, path: Sequence[str | int] = ()) -> object:
        value = self.value
        for part in path:
            if (
                isinstance(value, dict) and isinstance(part, str) and part in value
            ) or (
                isinstance(value, list)
                and type(part) is int
                and 0 <= part < len(value)
            ):
                value = value[part]
            else:
                raise KeyError("path does not identify an existing draft value")
        return value

    def replace_json(self, path: Sequence[str | int], raw_json: str) -> None:
        """Replace one JSON-compatible subtree with one fully parsed JSON value."""
        current = self.at(path)
        if not _is_json_value(current):
            raise TypeError("selected native value is not losslessly JSON-editable")
        try:
            replacement = json.loads(raw_json, parse_constant=_reject_json_constant)
        except ValueError as exc:
            raise ValueError("replacement must be one finite JSON value") from exc
        if not path:
            self.value = replacement
            return
        parent = self.at(path[:-1])
        part = path[-1]
        if (
            isinstance(parent, dict) and isinstance(part, str) and part in parent
        ) or (
            isinstance(parent, list)
            and type(part) is int
            and 0 <= part < len(parent)
        ):
            parent[part] = replacement
        else:
            raise KeyError("path does not identify an existing draft value")


@dataclass(frozen=True)
class SessionSnapshot:
    references: tuple[ObjectReference, ...]
    draft: LoomDraft | None


class LoomSession:
    """Navigate one synchronous Loom while keeping all drafts client-local."""

    def __init__(self, execute: Callable[[object, str | None], object]) -> None:
        if not callable(execute):
            raise TypeError("execute capability must be callable")
        self._execute = execute
        self.references: tuple[ObjectReference, ...] = ()
        self.draft: LoomDraft | None = None
        self.history: list[SessionSnapshot] = []

    def resolve(self, value: object, object_id: str | None = None) -> tuple[ObjectReference, ...]:
        """Execute once and install the validated result only after complete success."""
        result = self._execute(copy.deepcopy(value), object_id)
        references = _references(result)
        if self.references or self.draft is not None:
            self.history.append(self._snapshot())
        self.references = references
        self.draft = None
        return references

    def inspect(self, index: int) -> LoomDraft:
        """Open exactly the selected row without calling the provider."""
        reference = self.references[index]
        self.draft = LoomDraft.from_reference(reference)
        return self.draft

    def execute_draft(self, draft: LoomDraft | None = None) -> tuple[ObjectReference, ...]:
        """Execute one explicit draft; exceptions leave all local state untouched."""
        selected = draft if draft is not None else self.draft
        if selected is None:
            raise ValueError("no Loom draft is selected")
        return self.resolve(selected.value, selected.reference.object_id)

    def back(self) -> bool:
        """Restore client history without provider calls or undo semantics."""
        if not self.history:
            return False
        snapshot = self.history.pop()
        self.references = _copy_references(snapshot.references)
        self.draft = copy.deepcopy(snapshot.draft)
        return True

    def _snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            references=_copy_references(self.references),
            draft=copy.deepcopy(self.draft),
        )


def _references(value: object) -> tuple[ObjectReference, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise LoomResultError("Loom execute must return an ordered reference sequence")
    references: list[ObjectReference] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {
            "object_id",
            "description",
            "value",
        }:
            raise LoomReferenceError(
                f"Loom reference {index} must contain exactly object_id, description and value"
            )
        object_id = item["object_id"]
        description = item["description"]
        if not isinstance(object_id, str) or not object_id.strip():
            raise LoomReferenceError(f"Loom reference {index} object_id must be non-empty string")
        if not isinstance(description, str) or not description.strip():
            raise LoomReferenceError(
                f"Loom reference {index} description must be non-empty string"
            )
        references.append(
            ObjectReference(object_id, description, copy.deepcopy(item["value"]))
        )
    return tuple(references)


def _copy_references(references: Sequence[ObjectReference]) -> tuple[ObjectReference, ...]:
    return tuple(
        ObjectReference(item.object_id, item.description, copy.deepcopy(item.value))
        for item in references
    )


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def _reject_json_constant(_value: str) -> object:
    raise ValueError("non-finite numbers are not JSON")
