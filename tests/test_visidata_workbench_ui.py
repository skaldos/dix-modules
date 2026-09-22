from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

pytest.importorskip("visidata")

ROOT = Path(__file__).parents[1] / "visidata"
sys.path.insert(0, str(ROOT))

from skaldos_workbench.binding import bind_profile
from skaldos_workbench.branding import logo_command
from skaldos_workbench.draft import JsonDraft
from skaldos_workbench.roba_cli import AccessError
from skaldos_workbench.ui import JsonDraftSheet


class FakeAccess:
    def __init__(self) -> None:
        self.value = {"state": {"active_group": "", "groups": ["dix-dev", "evia"]}}
        self.writes: list[object] = []
        self.fail = False

    def get_key(self) -> object:
        return copy.deepcopy(self.value)

    def set_key(self, value: object) -> None:
        if self.fail:
            raise AccessError("failed")
        self.writes.append(copy.deepcopy(value))
        self.value = copy.deepcopy(value)


def sheet(access: FakeAccess) -> JsonDraftSheet:
    profile = bind_profile(
        ROOT / "templates/roba-key.toml", ROOT / "templates/profile.toml", access,
    )
    result = JsonDraftSheet(JsonDraft(profile), logo="roba")
    result.reload()
    return result


def test_drill_edit_apply_without_implicit_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from visidata import vd

    access = FakeAccess()
    root = sheet(access)
    assert root.getCommand("edit-json-scalar") is not None
    assert root.getCommand("apply-whole-key") is not None
    assert root.getCommand("Shift+B").longname == "show-brand-logo"
    state = root.openRow(root.rows[0])
    groups = state.openRow(state.rows[1])
    assert groups.rows[1]["path"] == ("state", "groups", 1)

    monkeypatch.setattr(vd, "input", lambda *args, **kwargs: '"new"')
    monkeypatch.setattr(vd, "status", lambda *args, **kwargs: None)
    groups.editRow(groups.rows[1])
    assert access.writes == []
    assert "*draft*" in groups.name
    assert groups.draft.at(("state", "groups", 1)) == "new"
    groups.applyDraft()
    assert access.writes == [
        {"state": {"active_group": "", "groups": ["dix-dev", "new"]}}
    ]
    assert "*draft*" not in groups.name


def test_apply_failure_keeps_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    from visidata import vd

    access = FakeAccess()
    root = sheet(access)
    root.draft.replace(("state", "active_group"), '"evia"')
    access.fail = True

    def fail(message):
        raise ValueError(message)

    monkeypatch.setattr(vd, "fail", fail)
    with pytest.raises(ValueError, match="draft retained"):
        root.applyDraft()
    assert root.draft.dirty
    assert access.writes == []


def test_both_png_logo_commands_are_exact() -> None:
    for logo in ("dix", "roba"):
        argv = logo_command(logo)
        assert argv[:7] == ["chafa", "--fill", "block", "-c", "full", "--scale", "0.5"]
        assert Path(argv[7]).is_file()
