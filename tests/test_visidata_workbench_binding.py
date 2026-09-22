from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "visidata"
sys.path.insert(0, str(ROOT))

from skaldos_workbench.binding import bind_profile
from skaldos_workbench.draft import JsonDraft
from skaldos_workbench.roba_cli import AccessError, RobaCliAccess


class FakeAccess:
    def __init__(self, value: object) -> None:
        self.value = copy.deepcopy(value)
        self.writes: list[object] = []
        self.fail = False

    def get_key(self) -> object:
        return copy.deepcopy(self.value)

    def set_key(self, value: object) -> None:
        if self.fail:
            raise AccessError("fake failure")
        self.writes.append(copy.deepcopy(value))
        self.value = copy.deepcopy(value)


def templates(access: FakeAccess):
    return bind_profile(
        ROOT / "templates/roba-key.toml", ROOT / "templates/profile.toml", access,
    )


def test_two_instances_and_explicit_whole_key_apply() -> None:
    first = FakeAccess({"state": {"active_group": "", "groups": ["dix-dev", "evia"]}})
    second = FakeAccess({"state": {"active_group": "private", "groups": ["private"]}})
    draft_a = JsonDraft(templates(first))
    draft_b = JsonDraft(templates(second))
    draft_a.replace(("state", "active_group"), '"dix-dev"')
    draft_a.replace(("state", "groups", 1), '"evia-new"')
    assert draft_a.dirty and not draft_b.dirty
    assert first.writes == [] and second.writes == []
    assert draft_a.apply() is True
    assert first.writes == [
        {"state": {"active_group": "dix-dev", "groups": ["dix-dev", "evia-new"]}}
    ]
    assert second.value == {"state": {"active_group": "private", "groups": ["private"]}}
    assert not draft_a.dirty
    assert draft_a.apply() is False


def test_failed_apply_retains_draft() -> None:
    access = FakeAccess({"nested": {"value": 1}})
    draft = JsonDraft(templates(access))
    draft.replace(("nested", "value"), "2")
    access.fail = True
    with pytest.raises(AccessError):
        draft.apply()
    assert draft.dirty and draft.at(("nested", "value")) == 2
    assert access.writes == []
    access.fail = False
    assert draft.apply() is True


@pytest.mark.parametrize("raw", ["not-json", "NaN"])
def test_inline_edit_rejects_invalid_or_container(raw: str) -> None:
    draft = JsonDraft(templates(FakeAccess({"value": "old"})))
    with pytest.raises(ValueError):
        draft.replace(("value",), raw)
    assert not draft.dirty


@pytest.mark.parametrize("raw", ["{}", "[]"])
def test_inline_edit_rejects_container(raw: str) -> None:
    draft = JsonDraft(templates(FakeAccess({"value": "old"})))
    with pytest.raises(TypeError):
        draft.replace(("value",), raw)
    assert not draft.dirty


def test_template_contract_rejects_unknown_operations(tmp_path: Path) -> None:
    profile = tmp_path / "profile.toml"
    profile.write_text('[profile]\nname="profile"\nfield="state"\nget="exec"\nset="set_key"\n')
    with pytest.raises(ValueError, match="operation names"):
        bind_profile(ROOT / "templates/roba-key.toml", profile, FakeAccess({}))


def test_cli_access_uses_exact_argv_and_no_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary = tmp_path / "dix-roba-cli"
    binary.touch()
    seen: list[list[str]] = []

    def run(argv, **kwargs):
        seen.append(argv)
        assert kwargs == {"capture_output": True, "text": True, "check": False, "timeout": 10.0}
        return subprocess.CompletedProcess(argv, 0, '{"groups":[1,2]}\n' if argv[2] == "get" else "true\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    access = RobaCliAccess(binary, "unix:/tmp/context/sockets/rw.sock", "profile")
    assert access.get_key() == {"groups": [1, 2]}
    access.set_key({"groups": [2, 3]})
    assert seen[0] == [str(binary), "data", "get", "--locator", access.locator, "--key", "profile"]
    assert seen[1] == [str(binary), "data", "set", "--locator", access.locator, "--key", "profile", "--value_json", json.dumps({"groups": [2, 3]}, separators=(",", ":"))]
    assert all("--token" not in argv for argv in seen)


def test_cli_errors_are_value_free(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    binary = tmp_path / "dix-roba-cli"
    binary.touch()
    monkeypatch.setattr(
        subprocess, "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1, "", "secret value leaked"),
    )
    access = RobaCliAccess(binary, "unix:/tmp/context/sockets/rw.sock", "profile")
    with pytest.raises(AccessError, match="exit 1") as exc:
        access.set_key({"sensitive": "payload"})
    assert "secret" not in str(exc.value) and "payload" not in str(exc.value)


def test_cli_requires_capability_locator(tmp_path: Path) -> None:
    binary = tmp_path / "dix-roba-cli"
    binary.touch()
    with pytest.raises(ValueError, match="capability"):
        RobaCliAccess(binary, "id:default", "profile")
