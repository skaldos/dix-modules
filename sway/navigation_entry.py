from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

_DIRECTIONS = ("left", "right", "up", "down")


class Api:
    def __init__(self, values: dict[str, Callable[..., object]]):
        self.values = values

    def require(self, name: str) -> Callable[..., object]:
        return self.values[name]


class LazyApi:
    def __init__(self, factory: Callable[[], object], names: tuple[str, ...]):
        self.factory, self.names = factory, names
        self.runtime: object | None = None

    def require(self, name: str) -> Callable[..., object]:
        if name not in self.names:
            raise KeyError(name)
        if self.runtime is None:
            self.runtime = self.factory()
        return getattr(self.runtime, name)


def execute(
    module_root: Path,
    direction: str,
    strategy: str,
    arguments: list[str] | None = None,
) -> dict[str, object]:
    if direction not in _DIRECTIONS:
        raise ValueError(f"unsupported direction: {direction!r}")
    arguments = [] if arguments is None else arguments
    ipc, basic = _basic_runtime(module_root)
    return _execute_with_runtime(module_root, direction, strategy, arguments, ipc, basic)


def _execute_with_runtime(
    module_root: Path,
    direction: str,
    strategy: str,
    arguments: list[str],
    ipc: object,
    basic: object,
) -> dict[str, object]:
    window_ids = _route_arguments(strategy, arguments)
    nav_mod = _runtime(module_root / "apps/nav/runtime.py", "skaldos_sway_nav")
    nav = nav_mod.Runtime(
        context=None,
        config={},
        basic_nav=_api(basic, _DIRECTIONS),
        windows_list_nav=LazyApi(
            lambda: _windows_list_runtime(module_root, ipc, basic), _DIRECTIONS
        ),
    )
    return _result(nav, direction, strategy, window_ids)


def _route_arguments(strategy: str, arguments: list[str]) -> list[int] | None:
    if strategy == "basic":
        if arguments:
            raise ValueError("basic strategy does not accept window IDs")
        return None
    if strategy == "windows-list":
        return _window_ids(arguments)
    return None


def _windows_list_runtime(module_root: Path, ipc: object, basic: object) -> object:
    window_list_mod = _runtime(
        module_root / "compositions/windows_list_nav/runtime.py",
        "skaldos_sway_windows_list_nav",
    )
    return window_list_mod.Runtime(
        context=None,
        config={},
        basic_nav=_api(basic, _DIRECTIONS),
        ipc=_ipc_api(ipc),
    )


def main(argv: list[str] | None = None, module_root: Path | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in _DIRECTIONS:
        value = "missing" if not arguments else arguments[0]
        print(f"argument error: unsupported direction: {value!r}", file=sys.stderr)
        return 2
    direction = arguments.pop(0)
    requested = arguments.pop(0) if arguments else "missing"
    root = module_root or Path(__file__).resolve().parent
    try:
        ipc, basic = _basic_runtime(root)
    except Exception as setup:  # noqa: BLE001
        print(f"runtime error: {_one_line(setup)}", file=sys.stderr)
        return 1
    try:
        result = _execute_with_runtime(root, direction, requested, arguments, ipc, basic)
    except Exception as primary:  # noqa: BLE001
        if requested == "basic" and not arguments:
            print(f"runtime error: {_one_line(primary)}", file=sys.stderr)
            return 1
        print(f"primary error: {_one_line(primary)}", file=sys.stderr)
        try:
            result = _result(basic, direction)
        except Exception as fallback:  # noqa: BLE001
            print(f"fallback error: {_one_line(fallback)}", file=sys.stderr)
            return 1
        envelope = _envelope(requested, "basic", True, result)
    else:
        envelope = _envelope(requested, requested, False, result)
    print(json.dumps(envelope, sort_keys=True, separators=(",", ":")))
    return 0


def _basic_runtime(module_root: Path) -> tuple[object, object]:
    ipc_mod = _runtime(module_root / "compositions/ipc/runtime.py", "skaldos_sway_ipc")
    basic_mod = _runtime(
        module_root / "compositions/basic_nav/runtime.py", "skaldos_sway_basic_nav"
    )
    ipc = ipc_mod.Runtime(context=None, config={})
    basic = basic_mod.Runtime(context=None, config={}, ipc=_ipc_api(ipc))
    return ipc, basic


def _ipc_api(ipc: object) -> Api:
    return _api(
        ipc,
        (
            "focused_con_id",
            "focus_direction",
            "focus_con_id",
            "live_con_ids",
            "navigation_topology",
        ),
    )


def _api(runtime: object, names: tuple[str, ...]) -> Api:
    return Api({name: getattr(runtime, name) for name in names})


def _result(runtime: object, direction: str, *arguments: object) -> dict[str, object]:
    result = getattr(runtime, direction)(*arguments)
    if not isinstance(result, dict):
        raise TypeError("navigation result must be a dictionary")
    return result


def _window_ids(arguments: list[str]) -> list[int]:
    result: list[int] = []
    for raw in arguments:
        if not raw.isascii() or not raw.isdecimal() or raw.startswith("0"):
            raise ValueError(f"window ID must be a canonical positive integer: {raw!r}")
        value = int(raw)
        if value <= 0:
            raise ValueError(f"window ID must be positive: {raw!r}")
        result.append(value)
    if len(set(result)) != len(result):
        raise ValueError("window IDs must not contain duplicates")
    return result


def _envelope(
    requested: str, executed: str, fallback: bool, result: dict[str, object]
) -> dict[str, object]:
    return {
        "requested": requested,
        "executed": executed,
        "fallback": fallback,
        "result": result,
    }


def _one_line(error: BaseException) -> str:
    return " ".join(str(error).splitlines()) or type(error).__name__


def _runtime(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load runtime: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
