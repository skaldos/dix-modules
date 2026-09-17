from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def _clients():
    full = {
        "border": "#010203",
        "background": "#040506",
        "text": "#070809",
        "indicator": "#0A0B0C",
        "child_border": "#0D0E0F",
    }
    return {
        "focused": dict(full),
        "focused_inactive": dict(full),
        "focused_tab_title": {key: full[key] for key in ("border", "background", "text")},
        "unfocused": dict(full),
        "urgent": dict(full),
    }


def _loaded(tmp_path, background=None):
    return {
        "id": "dix",
        "path": str(tmp_path / "dix.toml"),
        "clients": _clients(),
        "background": background,
    }


def _application(load_runtime, api, tmp_path, events, background=None, fail=None):
    Runtime = load_runtime("sway/apps/themes/runtime.py")
    loaded = _loaded(tmp_path, background)

    def record(name, result=None):
        def call(*arguments):
            events.append((name, arguments))
            if name == fail:
                raise RuntimeError(f"failed at {name}")
            return result

        return call

    files = api(
        create=record("create", str(tmp_path / "new.toml")),
        list=record("list", ["dix", "roba"]),
        load=record("load", loaded),
    )
    ipc = api(
        **{
            name: record(name)
            for name in (
                "set_focused",
                "set_focused_inactive",
                "set_focused_tab_title",
                "set_unfocused",
                "set_urgent",
                "set_background_file",
                "set_background_color",
            )
        }
    )
    active = api(set=record("active.set"), get=record("active.get", "dix"))
    return Runtime(
        context=None, config={}, theme_files=files, theme_ipc=ipc, active_theme=active
    )


def test_active_theme_missing_corrupt_and_atomic_set(load_runtime, tmp_path, monkeypatch):
    Runtime = load_runtime("sway/compositions/active_theme/runtime.py")
    path = tmp_path / "state" / "active-theme"
    runtime = Runtime(context=None, config={"path": str(path)})

    assert runtime.get() == ""
    assert runtime.set("dix") is None
    assert path.read_bytes() == b"dix\n"
    assert runtime.get() == "dix"
    assert not list(path.parent.glob(".active-theme.*"))

    path.write_bytes(b"dix\nextra\n")
    with pytest.raises(ValueError, match="exactly one"):
        runtime.get()

    monkeypatch.setenv("SKALDOS_SWAY_ACTIVE_THEME_FILE", str(tmp_path / "environment"))
    configured = Runtime(context=None, config={"path": str(tmp_path / "configured")})
    configured.set("roba")
    configured.set("dix", str(tmp_path / "explicit"))
    assert (tmp_path / "configured").read_bytes() == b"roba\n"
    assert (tmp_path / "explicit").read_bytes() == b"dix\n"


@pytest.mark.parametrize("payload", [b"", b"UPPER\n", b"two words\n", b"dix", b"\xff\n"])
def test_active_theme_rejects_every_noncanonical_marker(load_runtime, tmp_path, payload):
    Runtime = load_runtime("sway/compositions/active_theme/runtime.py")
    path = tmp_path / "active"
    path.write_bytes(payload)
    runtime = Runtime(context=None, config={"path": str(path)})
    with pytest.raises(ValueError, match="exactly one"):
        runtime.get()


def test_projection_methods_delegate_without_crossing_boundaries(load_runtime, api, tmp_path):
    events = []
    app = _application(load_runtime, api, tmp_path, events)

    assert app.create("new", "/themes") == str(tmp_path / "new.toml")
    assert app.list("/themes") == ["dix", "roba"]
    shown = app.show("dix", "/themes")
    shown["id"] = "changed"
    assert app.current("/marker") == "dix"
    assert events == [
        ("create", ("new", "/themes")),
        ("list", ("/themes",)),
        ("load", ("dix", "/themes")),
        ("active.get", ("/marker",)),
    ]


@pytest.mark.parametrize(
    ("background", "background_event", "background_result"),
    [
        (None, None, "unchanged"),
        (
            {"type": "solid_color", "color": "#102030"},
            ("set_background_color", ("#102030",)),
            "solid_color",
        ),
        (
            {
                "type": "image",
                "file": "/themes/wallpaper.png",
                "mode": "fill",
                "fallback_color": "#102030",
            },
            ("set_background_file", ("/themes/wallpaper.png", "fill", "#102030")),
            "image",
        ),
    ],
)
def test_apply_has_exact_order_and_marks_only_after_ipc(
    load_runtime, api, tmp_path, background, background_event, background_result
):
    events = []
    app = _application(load_runtime, api, tmp_path, events, background)

    result = app.apply("dix", "/themes", "/marker")

    names = [name for name, _ in events]
    expected = [
        "load",
        "set_focused",
        "set_focused_inactive",
        "set_focused_tab_title",
        "set_unfocused",
        "set_urgent",
    ]
    if background_event:
        expected.append(background_event[0])
        assert background_event in events
    expected.append("active.set")
    assert names == expected
    assert events[-1] == ("active.set", ("dix", "/marker"))
    assert result == {
        "theme": "dix",
        "path": str(tmp_path / "dix.toml"),
        "background": background_result,
    }


@pytest.mark.parametrize("failure", ["set_focused", "set_urgent", "set_background_file"])
def test_apply_failure_never_updates_marker(load_runtime, api, tmp_path, failure):
    events = []
    app = _application(
        load_runtime,
        api,
        tmp_path,
        events,
        {
            "type": "image",
            "file": "/themes/wallpaper.png",
            "mode": "fill",
            "fallback_color": "#102030",
        },
        fail=failure,
    )

    with pytest.raises(RuntimeError, match=failure):
        app.apply("dix")
    assert "active.set" not in [name for name, _ in events]


def test_current_is_marker_projection_not_live_sway_inspection(load_runtime, tmp_path):
    Runtime = load_runtime("sway/compositions/active_theme/runtime.py")
    path = tmp_path / "active-theme"
    first_session = Runtime(context=None, config={"path": str(path)})
    first_session.set("dix")

    simulated_new_sway_session = Runtime(context=None, config={"path": str(path)})
    assert simulated_new_sway_session.get() == "dix"


def test_application_source_owns_no_files_or_raw_sway_commands() -> None:
    path = ROOT / "sway/apps/themes/runtime.py"
    source = path.read_text()
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
    assert not ({"os", "pathlib", "tempfile", "tomllib", "i3ipc"} & imports)
    assert "client.focused" not in source
    assert "output * bg" not in source


def test_application_manifest_has_only_three_separated_dependencies() -> None:
    manifest = (ROOT / "sway/apps/themes/app.toml").read_text()
    assert [line for line in manifest.splitlines() if line.startswith("[compositions.")] == [
        "[compositions.theme_files]",
        "[compositions.theme_ipc]",
        "[compositions.active_theme]",
    ]
