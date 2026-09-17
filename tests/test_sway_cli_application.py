from __future__ import annotations

import inspect

from dix.core.application import ApplicationApi, ApplicationFunctionDescriptor


def _api(application_id, functions):
    descriptors = {
        name: ApplicationFunctionDescriptor(
            id=name,
            application_id=application_id,
            source="local",
            origin=None,
            signature=inspect.signature(function),
            return_annotation=inspect.signature(function).return_annotation,
            docstring=function.__doc__,
        )
        for name, function in functions.items()
    }
    return ApplicationApi(functions, descriptors)


def _themes(calls):
    def create(theme: str, theme_dir: str = "") -> str:
        """Create a complete Sway theme."""
        calls.append(("create", theme, theme_dir))
        return f"{theme_dir}/{theme}.toml"

    def list_(theme_dir: str = "") -> list[str]:
        """List Sway themes."""
        calls.append(("list", theme_dir))
        return ["dix", "roba"]

    def list_lines(theme_dir: str = "") -> str:
        """List one Sway theme per line."""
        calls.append(("list_lines", theme_dir))
        return "dix\nroba"

    def show(theme: str, theme_dir: str = "") -> dict[str, object]:
        """Show one Sway theme."""
        calls.append(("show", theme, theme_dir))
        return {"id": theme}

    def apply(
        theme: str, theme_dir: str = "", active_theme_file: str = ""
    ) -> dict[str, object]:
        """Apply one complete Sway theme."""
        calls.append(("apply", theme, theme_dir, active_theme_file))
        return {"theme": theme}

    def current(active_theme_file: str = "") -> str:
        """Read the last successfully applied Sway theme."""
        calls.append(("current", active_theme_file))
        return "dix"

    return _api(
        "skaldos/sway/themes",
        {
            "create": create,
            "list": list_,
            "list_lines": list_lines,
            "show": show,
            "apply": apply,
            "current": current,
        },
    )


def test_cli_runtime_projects_group_and_theme_targets(load_runtime, api):
    Runtime = load_runtime("sway/apps/cli/runtime.py")
    captured = {}

    def invoke(**values):
        captured.update(values)
        return 0

    empty = _api("skaldos/sway/groups", {})
    themes = _themes([])
    runtime = Runtime(
        context=None, config={}, typer=api(invoke=invoke), groups=empty, themes=themes
    )

    assert runtime.main(["theme", "list"]) == 0
    assert set(captured["targets"]) == {"group", "theme"}
    assert {value.id for value in captured["targets"]["theme"].functions()} == {
        "create",
        "list",
        "list_lines",
        "show",
        "apply",
        "current",
    }


def test_real_typer_projection_uses_named_underscore_options(load_runtime, capsys):
    TyperRuntime = load_runtime("../dix/modules/dix/cli/compositions/typer/runtime.py")
    calls = []
    runtime = TyperRuntime(context=None, config={})

    result = runtime.invoke(
        name="skaldos-sway",
        targets={"theme": _themes(calls)},
        argv=[
            "theme",
            "apply",
            "--theme",
            "dix",
            "--theme_dir",
            "/themes",
            "--active_theme_file",
            "/state/active-theme",
        ],
    )

    assert result == 0, capsys.readouterr().err
    assert calls == [("apply", "dix", "/themes", "/state/active-theme")]


def test_theme_help_exposes_all_commands_and_named_paths(load_runtime, capsys):
    TyperRuntime = load_runtime("../dix/modules/dix/cli/compositions/typer/runtime.py")
    runtime = TyperRuntime(context=None, config={})
    themes = _themes([])

    assert runtime.invoke(name="skaldos-sway", targets={"theme": themes}, argv=["theme", "--help"]) == 0
    help_text = capsys.readouterr().out
    for command in ("create", "list", "list_lines", "show", "apply", "current"):
        assert command in help_text

    assert runtime.invoke(
        name="skaldos-sway", targets={"theme": themes}, argv=["theme", "list_lines"]
    ) == 0
    assert capsys.readouterr().out == "dix\nroba\n"

    assert runtime.invoke(
        name="skaldos-sway", targets={"theme": themes}, argv=["theme", "apply", "--help"]
    ) == 0
    apply_help = capsys.readouterr().out
    assert "--theme" in apply_help
    assert "--theme_dir" in apply_help
    assert "--active_theme_file" in apply_help
