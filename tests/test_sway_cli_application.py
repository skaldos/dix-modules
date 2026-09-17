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


def _themed_groups(calls):
    def list_(themed_group_dir: str = "") -> dict[str, str]:
        """List persistent group-to-theme assignments."""
        calls.append(("list", themed_group_dir))
        return {"work": "dix"}

    def load(
        themed_group_dir: str = "", theme_dir: str = ""
    ) -> dict[str, object]:
        """Reconstruct declared themed groups."""
        calls.append(("load", themed_group_dir, theme_dir))
        return {"managed_groups": ["work"]}

    def select(
        group: str,
        themed_group_dir: str = "",
        theme_dir: str = "",
        active_theme_file: str = "",
    ) -> dict[str, object]:
        """Select a group and apply its assigned theme."""
        calls.append(
            ("select", group, themed_group_dir, theme_dir, active_theme_file)
        )
        return {"group": group}

    return _api(
        "skaldos/sway/themed_groups",
        {"list": list_, "load": load, "select": select},
    )


def test_cli_runtime_projects_group_theme_and_themed_group_targets(load_runtime, api):
    Runtime = load_runtime("sway/apps/cli/runtime.py")
    captured = {}

    def invoke(**values):
        captured.update(values)
        return 0

    empty = _api("skaldos/sway/groups", {})
    themes = _themes([])
    themed_groups = _themed_groups([])
    runtime = Runtime(
        context=None,
        config={},
        typer=api(invoke=invoke),
        groups=empty,
        themes=themes,
        themed_groups=themed_groups,
    )

    assert runtime.main(["theme", "list"]) == 0
    assert set(captured["targets"]) == {"group", "theme", "themed_group"}
    assert {value.id for value in captured["targets"]["theme"].functions()} == {
        "create",
        "list",
        "list_lines",
        "show",
        "apply",
        "current",
    }
    assert {value.id for value in captured["targets"]["themed_group"].functions()} == {
        "list",
        "load",
        "select",
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


def test_themed_group_projection_keeps_function_and_option_underscores(
    load_runtime, capsys
):
    TyperRuntime = load_runtime("../dix/modules/dix/cli/compositions/typer/runtime.py")
    calls = []
    runtime = TyperRuntime(context=None, config={})
    themed_groups = _themed_groups(calls)

    result = runtime.invoke(
        name="skaldos-sway",
        targets={"themed_group": themed_groups},
        argv=[
            "themed_group",
            "select",
            "--group",
            "work",
            "--themed_group_dir",
            "/definitions",
            "--theme_dir",
            "/themes",
            "--active_theme_file",
            "/state/active-theme",
        ],
    )

    assert result == 0, capsys.readouterr().err
    assert calls == [
        (
            "select",
            "work",
            "/definitions",
            "/themes",
            "/state/active-theme",
        )
    ]

    assert runtime.invoke(
        name="skaldos-sway",
        targets={"themed_group": themed_groups},
        argv=["themed_group", "load", "--help"],
    ) == 0
    help_text = capsys.readouterr().out
    assert "--themed_group_dir" in help_text
    assert "--theme_dir" in help_text
