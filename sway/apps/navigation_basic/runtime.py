from __future__ import annotations

import importlib.util
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol


class Api(Protocol):
    def require(self, function_id: str) -> Callable[..., object]: ...


class Runtime:
    def __init__(
        self,
        *,
        context: object,
        config: Mapping[str, object],
        ipc: Api,
    ) -> None:
        self.context, self.config = context, config
        path = Path(__file__).parents[2] / "compositions/basic_nav/runtime.py"
        spec = importlib.util.spec_from_file_location("skaldos_sway_basic_nav_adapter", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load basic_nav runtime: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        delegate = module.Runtime(context=context, config=config, ipc=ipc)
        self._require = lambda name: getattr(delegate, name)

    def left(self) -> dict[str, object]:
        return self._call("left")

    def right(self) -> dict[str, object]:
        return self._call("right")

    def up(self) -> dict[str, object]:
        return self._call("up")

    def down(self) -> dict[str, object]:
        return self._call("down")

    def _call(self, direction: str) -> dict[str, object]:
        result = self._require(direction)()
        if not isinstance(result, dict):
            raise TypeError("basic navigation result must be a dictionary")
        return result
