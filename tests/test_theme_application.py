from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

import i3ipc
import pytest
from dix.core import ApplicationComponent, ModuleComponent, create_core_component_registry
from dix.core.application import ApplicationInstanceSpec
from dix.modules import first_party_module_path

ROOT = Path(__file__).parents[1]


class Reply:
    success = True
    error = ""


class RecordingConnection:
    commands: ClassVar[list[str]] = []
    fail_at: ClassVar[int | None] = None

    def command(self, value: str) -> list[Reply]:
        self.commands.append(value)
        if self.fail_at == len(self.commands):
            reply = Reply()
            reply.success = False
            reply.error = "test IPC failure"
            return [reply]
        return [Reply()]


class FakeApi:
    def __init__(self, execute: Callable[[object], object]) -> None:
        self.execute = execute

    def require(self, function_id: str) -> Callable[..., object]:
        assert function_id == "execute"
        return self.execute


def _colors(start: int) -> dict[str, str]:
    return {
        "border": f"#{start:06x}",
        "background": f"#{start + 1:06x}",
        "text": f"#{start + 2:06x}",
        "indicator": f"#{start + 3:06x}",
        "child_border": f"#{start + 4:06x}",
    }


def _full_theme() -> dict[str, object]:
    return {
        "focused": _colors(1),
        "focused_inactive": _colors(10),
        "focused_tab_title": {
            "border": "#111111",
            "background": "#222222",
            "text": "#333333",
        },
        "unfocused": _colors(20),
        "urgent": _colors(30),
        "background": {
            "type": "image",
            "file": "wallpapers/example.png",
            "mode": "fit",
            "fallback_color": "#000000",
        },
    }


def _toml(theme: dict[str, object]) -> str:
    lines: list[str] = []
    for name, value in theme.items():
        assert isinstance(value, dict)
        lines.append(f"[{name}]")
        for key, item in value.items():
            lines.append(f'{key} = "{item}"')
        lines.append("")
    return "\n".join(lines)


def _application(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    RecordingConnection.commands = []
    RecordingConnection.fail_at = None
    monkeypatch.setattr(i3ipc, "Connection", RecordingConnection)
    registry = create_core_component_registry()
    modules = registry.require("module", ModuleComponent)
    applications = registry.require("application", ApplicationComponent)
    modules.load_module(first_party_module_path("dix/cli"), module_id="dix/cli")
    modules.load_module(ROOT / "sway/core", module_id="skaldos/sway/core")
    modules.load_module(first_party_module_path("dix/norn"), module_id="dix/norn")
    modules.load_module(ROOT / "sway/theme", module_id="skaldos/sway/theme")
    return applications.create_instance(
        ApplicationInstanceSpec("theme", "skaldos/sway/theme/theme", {}, tmp_path),
        owner_scope_id="theme-application-test",
    )


def test_apply_delegates_the_complete_root_mapping_exactly_once(tmp_path: Path) -> None:
    path = tmp_path / "theme.toml"
    path.write_text(_toml(_full_theme()))
    calls: list[object] = []
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda value: calls.append(value) or {}))  # type: ignore[arg-type]

    assert runtime.apply(str(path)) is None
    assert calls == [_full_theme()]


def test_apply_passes_the_parser_root_object_without_copying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "theme.toml"
    path.write_text("")
    document = _full_theme()
    calls: list[object] = []
    from sway.theme.apps.theme import runtime as theme_runtime

    monkeypatch.setattr(theme_runtime.tomllib, "load", lambda _stream: document)
    runtime = theme_runtime.Runtime(
        context=object(),
        config={},
        client_theme=FakeApi(lambda value: calls.append(value) or {}),
    )  # type: ignore[arg-type]

    assert runtime.apply(str(path)) is None
    assert len(calls) == 1
    assert calls[0] is document


def test_apply_expands_user_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "theme.toml"
    path.write_text("")
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list[object] = []
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda value: calls.append(value) or {}))  # type: ignore[arg-type]
    assert runtime.apply("~/theme.toml") is None
    assert calls == [{}]


@pytest.mark.parametrize("value", ["", 1, None])
def test_apply_rejects_an_invalid_file_argument_without_delegation(value: object) -> None:
    calls: list[object] = []
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda item: calls.append(item) or {}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty string"):
        runtime.apply(value)  # type: ignore[arg-type]
    assert calls == []


def test_apply_rejects_missing_directory_and_invalid_toml_before_delegation(
    tmp_path: Path,
) -> None:
    calls: list[object] = []
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda item: calls.append(item) or {}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a regular file"):
        runtime.apply(str(tmp_path / "missing.toml"))
    with pytest.raises(ValueError, match="not a regular file"):
        runtime.apply(str(tmp_path))
    invalid = tmp_path / "invalid.toml"
    invalid.write_text("[broken")
    with pytest.raises(Exception) as captured:
        runtime.apply(str(invalid))
    assert type(captured.value).__name__ == "TOMLDecodeError"
    assert calls == []


def test_apply_surfaces_unreadable_file_before_delegation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unreadable.toml"
    path.write_text("")
    path.chmod(0)
    calls: list[object] = []
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda item: calls.append(item) or {}))  # type: ignore[arg-type]
    try:
        if os.access(path, os.R_OK):
            pytest.skip("current user can read a mode-000 file")
        with pytest.raises(PermissionError):
            runtime.apply(str(path))
        assert calls == []
    finally:
        path.chmod(0o600)


def test_apply_requires_a_dictionary_knot_result(tmp_path: Path) -> None:
    path = tmp_path / "theme.toml"
    path.write_text("")
    from sway.theme.apps.theme.runtime import Runtime

    runtime = Runtime(context=object(), config={}, client_theme=FakeApi(lambda _value: None))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must return a dictionary"):
        runtime.apply(str(path))


def test_real_graph_applies_four_known_fields_and_ignores_future_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path, monkeypatch)
    theme = _full_theme()
    path = tmp_path / "full.toml"
    path.write_text(_toml(theme))

    assert application.api.require("apply")(str(path)) is None
    assert RecordingConnection.commands == [
        f"client.{name} " + " ".join(theme[name].values())  # type: ignore[union-attr]
        for name in ("focused", "focused_inactive", "unfocused", "urgent")
    ]


def test_real_graph_noops_without_known_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path, monkeypatch)
    path = tmp_path / "future.toml"
    path.write_text('[background]\ntype = "solid"\ncolor = "#000000"\n')
    assert application.api.require("apply")(str(path)) is None
    assert RecordingConnection.commands == []


def test_real_graph_preserves_partial_effect_on_late_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path, monkeypatch)
    theme = _full_theme()
    theme["urgent"] = {**_colors(30), "text": "invalid"}
    path = tmp_path / "late-error.toml"
    path.write_text(_toml(theme))

    with pytest.raises(Exception) as captured:
        application.api.require("apply")(str(path))
    assert type(captured.value).__name__ == "SwayColorError"
    assert len(RecordingConnection.commands) == 3


def test_real_graph_preserves_partial_effect_on_late_ipc_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path, monkeypatch)
    path = tmp_path / "late-ipc-error.toml"
    path.write_text(_toml(_full_theme()))
    RecordingConnection.fail_at = 4

    with pytest.raises(Exception) as captured:
        application.api.require("apply")(str(path))
    assert type(captured.value).__name__ == "SwayIpcError"
    assert len(RecordingConnection.commands) == 4


def test_real_graph_parse_failure_happens_before_ipc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path, monkeypatch)
    path = tmp_path / "invalid.toml"
    path.write_text("focused = [")

    with pytest.raises(Exception) as captured:
        application.api.require("apply")(str(path))
    assert type(captured.value).__name__ == "TOMLDecodeError"
    assert RecordingConnection.commands == []
