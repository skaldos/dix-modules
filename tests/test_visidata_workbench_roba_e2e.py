"""Real two-Context DIX CLI pressure test; no host daemon or stored secrets."""

from __future__ import annotations

import ast
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "visidata"))

from skaldos_workbench.binding import bind_profile
from skaldos_workbench.draft import JsonDraft
from skaldos_workbench.roba_cli import AccessError, RobaCliAccess


def test_real_roba_cli_two_contexts_and_capability_rights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dix_root = Path(os.environ.get("DIX_REPOSITORY", "/cwd/repos/dix"))
    dix_python = Path(os.environ.get("DIX_PYTHON", dix_root / ".venv/bin/python"))
    assert dix_python.is_file(), "DIX Python must be installed for real CLI test"
    spec = dix_root / "examples/launchers/dix_roba.toml"
    assert spec.is_file(), "pinned DIX source must contain its ROBA launcher spec"

    with TemporaryDirectory(prefix="u48-", dir="/tmp") as raw:
        temporary = Path(raw)
        home = temporary / "home"
        home.mkdir()
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("ROBA_", "DIX_ROBA_"))
        }
        for key in tuple(os.environ):
            if key.startswith(("ROBA_", "DIX_ROBA_")):
                monkeypatch.delenv(key)
        environment.update({
            "HOME": str(home),
            "XDG_RUNTIME_DIR": str(temporary / "run"),
            "XDG_STATE_HOME": str(temporary / "state"),
            "DIX_ROBA_RUNTIME_ROOT": str(temporary / "r"),
            "DIX_ROBA_LOGS_ROOT": str(temporary / "l"),
            "PYTHONPATH": str(dix_root / "src"),
        })
        (temporary / "run").mkdir(mode=0o700)
        for key, value in environment.items():
            if key in {"HOME", "XDG_RUNTIME_DIR", "XDG_STATE_HOME", "DIX_ROBA_RUNTIME_ROOT", "DIX_ROBA_LOGS_ROOT", "PYTHONPATH"}:
                monkeypatch.setenv(key, value)

        launcher = temporary / "dix_roba.py"
        built = subprocess.run(
            [str(dix_python), "-m", "dix.bootstrap", "build", str(spec),
             "--output", str(launcher), "--replace"],
            cwd=dix_root, env=environment, capture_output=True, text=True, check=False,
        )
        assert built.returncode == 0, "DIX launcher build failed"
        executable = temporary / "dix-roba-cli"
        executable.write_text(
            "#!/bin/sh\nexec " + shlex.quote(str(dix_python)) + " "
            + shlex.quote(str(launcher)) + ' "$@"\n',
            encoding="utf-8",
        )
        executable.chmod(0o755)

        def call(*arguments: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(executable), *arguments], cwd=dix_root, env=environment,
                capture_output=True, text=True, check=False, timeout=20,
            )

        def record(*arguments: str) -> dict[str, object]:
            result = call(*arguments)
            assert result.returncode == 0, f"CLI {arguments[:2]} failed"
            value = ast.literal_eval(result.stdout.strip())
            assert isinstance(value, dict)
            return value

        record("managed", "start")
        try:
            alpha = record("context", "create", "--context_id", "alpha")
            beta = record("context", "create", "--context_id", "beta")
            alpha_locator = str(alpha["context_locator"])
            beta_locator = str(beta["context_locator"])
            alpha_owner = str(alpha["owner_token"])
            beta_owner = str(beta["owner_token"])

            def socket(
                locator: str, owner: str, socket_id: str, *, read: bool, write: bool,
            ) -> str:
                arguments = ["socket", "create", "--locator", locator, "--token", owner,
                             "--socket_id", socket_id]
                if read:
                    arguments.extend(("--read", "context"))
                if write:
                    arguments.extend(("--write", "context"))
                result = record(*arguments)
                return "unix:" + str(result["socket"])

            alpha_rw = socket(alpha_locator, alpha_owner, "rw", read=True, write=True)
            beta_rw = socket(beta_locator, beta_owner, "rw", read=True, write=True)
            alpha_read = socket(alpha_locator, alpha_owner, "reader", read=True, write=False)
            alpha_write = socket(alpha_locator, alpha_owner, "writer", read=False, write=True)

            profile_path = ROOT / "visidata/templates/profile.toml"
            access_path = ROOT / "visidata/templates/roba-key.toml"

            def draft(locator: str) -> JsonDraft:
                return JsonDraft(bind_profile(
                    access_path, profile_path, RobaCliAccess(executable, locator, "profile"),
                ))

            alpha_access = RobaCliAccess(executable, alpha_rw, "profile")
            beta_access = RobaCliAccess(executable, beta_rw, "profile")
            alpha_access.set_key({"state": {"active_group": "", "groups": ["dix-dev"]}})
            beta_access.set_key({"state": {"active_group": "private", "groups": ["private"]}})
            RobaCliAccess(executable, alpha_rw, "neighbor").set_key({"keep": 17})

            alpha_draft = draft(alpha_rw)
            beta_draft = draft(beta_rw)
            alpha_draft.replace(("state", "active_group"), '"dix-dev"')
            alpha_draft.replace(("state", "groups", 0), '"dix-updated"')
            assert beta_draft.at(("state", "active_group")) == "private"
            assert alpha_draft.apply() is True
            assert alpha_access.get_key() == {
                "state": {"active_group": "dix-dev", "groups": ["dix-updated"]}
            }
            assert beta_access.get_key() == {
                "state": {"active_group": "private", "groups": ["private"]}
            }
            assert RobaCliAccess(executable, alpha_rw, "neighbor").get_key() == {"keep": 17}

            read_only = RobaCliAccess(executable, alpha_read, "profile")
            assert read_only.get_key() == alpha_access.get_key()
            with pytest.raises(AccessError, match="data set failed"):
                read_only.set_key({"bad": True})
            write_only = RobaCliAccess(executable, alpha_write, "profile")
            with pytest.raises(AccessError, match="data get failed"):
                write_only.get_key()
            write_only.set_key({"from_write_only": True})
            assert alpha_access.get_key() == {"from_write_only": True}
            assert beta_access.get_key() == {
                "state": {"active_group": "private", "groups": ["private"]}
            }
            assert json.loads(call(
                "data", "get", "--locator", alpha_rw, "--key", "neighbor",
            ).stdout.strip()) == {"keep": 17}
        finally:
            stopped = call("daemon", "stop")
            assert stopped.returncode == 0, "isolated daemon stop failed"
