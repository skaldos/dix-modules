from __future__ import annotations

import copy
import re


class Runtime:
    """Small test-only contracts, not product path/color implementations."""

    def __init__(self, *, context, config, text, number):
        self._kind = config.get("kind", "path")
        self._prefix = config.get("prefix", "")
        self._text, self._number = text, number
        self._calls = []

    def _process(self, boundary, value):
        self._calls.append((boundary, copy.deepcopy(value)))
        if self._kind == "any":
            return copy.deepcopy(value)
        if self._kind == "bytes":
            return b"not-native"
        shape = self._number if self._kind == "number" else self._text
        result = shape.require("process_" + boundary)(value)
        if self._kind == "color" and not re.fullmatch(r"#[0-9a-fA-F]{6}", result):
            raise ValueError("Invalid test color")
        if self._kind == "color":
            result = result.lower()
        return self._prefix + result if self._prefix and boundary == "output" else result

    def process_input(self, value: object) -> object:
        return self._process("input", value)

    def process_output(self, value: object) -> object:
        return self._process("output", value)

    def calls(self) -> list:
        return copy.deepcopy(self._calls)
