#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
BASE = "afbbdc3c45ebd296dfcb7e37f149f8a68953eb10"


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def verify() -> None:
    if git("branch", "--show-current") != "sway":
        raise AssertionError("verification must run on branch 'sway'")
    if git("rev-parse", "main") != BASE:
        raise AssertionError("main moved away from the approved source commit")
    if git("merge-base", "main", "HEAD") != BASE:
        raise AssertionError("branch 'sway' no longer starts at the approved source commit")

    paths = tuple(filter(None, git("ls-files").splitlines()))
    sway_children = {
        path.split("/", 2)[1]
        for path in paths
        if path.startswith("sway/") and "/" in path
    }
    if not sway_children <= {"README.md", "README.de.md", "requirements.txt", "core", "nav"}:
        raise AssertionError(f"unexpected Sway ownership: {sorted(sway_children)}")
    for prefix in ("sway/apps/", "sway/compositions/"):
        if any(path.startswith(prefix) for path in paths):
            raise AssertionError(f"monolithic module root remains: {prefix}")

    product_paths = tuple(
        path
        for path in paths
        if path.startswith(("sway/core/", "sway/nav/"))
    )
    forbidden_path_parts = ("group", "theme", "profile", "roba", "wofi", "state")
    for path in product_paths:
        lowered = path.lower()
        if any(part in lowered for part in forbidden_path_parts):
            raise AssertionError(f"removed feature remains in the product tree: {path}")

    delivery_paths = (
        "README.md",
        "README.de.md",
        "sway/README.md",
        "sway/README.de.md",
        *product_paths,
    )
    private_path = re.compile(r"/home/(?:mfulz|roba|codex)(?:/|\b)")
    secret = re.compile(r"(?:roba1\.(?:owner|read|write|grant)\.|BEGIN [A-Z ]+PRIVATE KEY)")
    for relative in delivery_paths:
        value = (ROOT / relative).read_text()
        if private_path.search(value):
            raise AssertionError(f"private home path leaked into {relative}")
        if secret.search(value):
            raise AssertionError(f"secret-shaped value leaked into {relative}")

    for relative in ("README.md", "README.de.md", "sway/README.md", "sway/README.de.md"):
        value = (ROOT / relative).read_text()
        for forbidden in ("/cwd/", "operations/", "--extra sway"):
            if forbidden in value:
                raise AssertionError(f"internal delivery term {forbidden!r} leaked into {relative}")
        if re.search(r"\b(?:DX|UP)-\d+\b", value):
            raise AssertionError(f"internal work identifier leaked into {relative}")


if __name__ == "__main__":
    verify()
    print("branch_scope=passed")
