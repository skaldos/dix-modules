from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None, module_root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(prog="skaldos-sway-json")
    parser.add_argument(
        "operation",
        choices=(
            "list-lines",
            "memberships-lines",
            "create",
            "add",
            "remove",
            "select",
            "deactivate",
            "current",
        ),
    )
    parser.add_argument("group", nargs="?")
    args = parser.parse_args(argv)
    needs_group = args.operation in {"create", "add", "remove", "select"}
    if needs_group != (args.group is not None):
        parser.error(
            "operation requires exactly one group argument"
            if needs_group
            else "operation accepts no group argument"
        )
    root = (module_root or Path(__file__).resolve().parent).resolve()
    try:
        app, cleanup = _application(root)
    except Exception as exc:  # noqa: BLE001
        print(f"runtime error: {exc}", file=sys.stderr)
        return 1
    try:
        if args.operation == "list-lines":
            value = app.api.require("list")()
            print("\n".join(value))
        elif args.operation == "memberships-lines":
            print("\n".join(app.api.require("memberships")()))
        else:
            fn = app.api.require(args.operation)
            value = fn(args.group) if args.group is not None else fn()
            print(json.dumps(value, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"runtime error: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup()


def _application(root: Path):
    from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
    from dix.core.application import ApplicationInstanceSpec
    from dix.modules import first_party_module_path

    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    apps = registry.require("application", ApplicationComponent)
    loaded = []
    try:
        for module_id in ("dix/state", "dix/cli", "dix/roba"):
            modules.load_module(first_party_module_path(module_id), module_id=module_id)
            loaded.append(module_id)
        modules.load_module(root, module_id="skaldos/sway")
        loaded.append("skaldos/sway")
        app = apps.create_instance(
            ApplicationInstanceSpec("management", "skaldos/sway/groups", {}, root),
            owner_scope_id="skaldos-sway-management",
        )
    except BaseException:
        for module_id in reversed(loaded):
            modules.unload_module(module_id)
        raise

    def cleanup():
        apps.destroy_instance("skaldos-sway-management", "management")
        for module_id in reversed(loaded):
            modules.unload_module(module_id)

    return app, cleanup


if __name__ == "__main__":
    raise SystemExit(main())
