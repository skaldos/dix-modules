from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
DOC_PATHS = (
    Path("README.md"),
    Path("README.de.md"),
    Path("sway/README.md"),
    Path("sway/README.de.md"),
)
PUBLIC_URLS = (
    "https://github.com/skaldos/dix",
    "https://github.com/skaldos/dix-modules",
    "https://github.com/skaldos/roba",
)
FORBIDDEN = (
    re.compile(r"\bDX-\d+\b"),
    re.compile(r"\bUP-\d+\b"),
    re.compile(r"/cwd/"),
    re.compile(r"\boperations/"),
    re.compile(r"--extra(?:=|\s+)sway\b"),
)


def _read(relative: Path) -> str:
    path = ROOT / relative
    if not path.is_file():
        raise AssertionError(f"public document is missing: {relative}")
    return path.read_text()


def _require(text: str, values: tuple[str, ...], label: str) -> None:
    missing = [value for value in values if value not in text]
    if missing:
        raise AssertionError(f"{label} is missing public evidence: {missing}")


def _heading_shape(text: str) -> list[int]:
    return [len(match.group(1)) for match in re.finditer(r"^(#+)\s", text, re.MULTILINE)]


def verify() -> None:
    docs = {relative: _read(relative) for relative in DOC_PATHS}
    root_en = docs[Path("README.md")]
    root_de = docs[Path("README.de.md")]
    sway_en = docs[Path("sway/README.md")]
    sway_de = docs[Path("sway/README.de.md")]

    if _heading_shape(root_en) != _heading_shape(root_de):
        raise AssertionError("root README language variants have different heading structure")
    if _heading_shape(sway_en) != _heading_shape(sway_de):
        raise AssertionError("Sway README language variants have different heading structure")

    _require(root_en, ("[Deutsch](README.de.md)",), "English root README")
    _require(root_de, ("[English](README.md)",), "German root README")
    _require(sway_en, ("[Deutsch](README.de.md)",), "English Sway README")
    _require(sway_de, ("[English](README.md)",), "German Sway README")

    for relative, text in docs.items():
        _require(text, PUBLIC_URLS, str(relative))
        _require(text, ("Public Alpha",), str(relative))
        for pattern in FORBIDDEN:
            if match := pattern.search(text):
                raise AssertionError(
                    f"{relative} exposes forbidden internal term: {match.group(0)!r}"
                )

    root_markers = (
        "dix/modules/skaldos",
        "skaldos/sway",
        "uv sync --frozen --extra dev --extra cli --extra state --extra roba",
        'uv pip install --python .venv/bin/python -r "$MODULES_ROOT/sway/requirements.txt"',
        "DIX_REPOSITORY=\"$DIX_ROOT\"",
        "Apache License 2.0",
    )
    _require(root_en, root_markers, "English root README")
    _require(root_de, root_markers, "German root README")

    detailed_markers = (
        "i3ipc==2.2.1",
        "git clone https://github.com/skaldos/roba.git roba",
        "git clone https://github.com/skaldos/dix.git dix",
        "git clone https://github.com/skaldos/dix-modules.git",
        '"$DIX_SOURCE_ROOT/modules/skaldos"',
        "SKALDOS_SWAY_GROUP_STATE_FILE",
        "SKALDOS_SWAY_ACTIVE_MEMBERS_FILE",
        "SKALDOS_SWAY_NAVIGATION_TARGET_FILE",
        "SKALDOS_SWAY_THEME_DIR",
        "SKALDOS_SWAY_THEMED_GROUP_DIR",
        "SKALDOS_SWAY_ACTIVE_THEME_FILE",
        "~/.roba/runtime",
        "~/.roba/logs",
        "DIX_ROBA_RUNTIME_ROOT",
        "DIX_ROBA_LOGS_ROOT",
        '"$SWAY_ROOT/integrations/install"',
        '"$HOME/.dix/env"',
        "DIX_LAUNCHERS",
        "dix-roba --help",
        "skaldos-sway --help",
        "managed start",
        "control create_context",
        "--context_id skaldos-sway",
        "skaldos-sway-nav",
        "skaldos-sway-json",
        "create work",
        "list_lines",
        "select work",
        "add work",
        "remove work",
        "deactivate",
        "skaldos-sway theme list",
        "skaldos-sway theme list_lines",
        "skaldos-sway theme show --theme dix",
        "skaldos-sway theme apply --theme dix",
        "skaldos-sway theme current",
        "skaldos-sway theme create --theme personal",
        "skaldos-sway themed_group list",
        "skaldos-sway themed_group load",
        "skaldos-sway themed_group select --group",
        "--themed_group_dir",
        "--theme_dir",
        "--active_theme_file",
        "--target basic",
        "--target group",
        "integrations/wofi/select",
        "integrations/wofi/add",
        "integrations/wofi/remove",
        "integrations/wofi/theme",
        "skaldos-sway-wofi-theme",
        "--no-custom-entry",
        "swaymsg reload",
        "daemon stop",
        "composition definition is not loaded: dix/cli/typer",
        "i3ipc",
        "python tests/verify_public_docs.py",
        "Apache License 2.0",
    )
    _require(sway_en, detailed_markers, "English Sway README")
    _require(sway_de, detailed_markers, "German Sway README")
    _require(sway_en, ("ROBA **persists nothing**",), "English persistence boundary")
    _require(sway_de, ("ROBA **persistiert nichts**",), "German persistence boundary")
    english_tool_markers = (
        "[No active group]",
        "[+ New group]",
        "Add window to group",
        "Remove window from group",
        "New group name",
    )
    _require(sway_en, english_tool_markers, "English public tool surface")
    _require(sway_de, english_tool_markers, "German public tool surface")

    for relative, text in docs.items():
        if relative.name.endswith(".de.md"):
            marker = (
                "Ausgelieferte Befehlsnamen, Prompts und\n"
                "maschinennahe Fehlermeldungen sind englisch."
            )
        else:
            marker = (
                "Shipped command names, prompts, and\n"
                "machine-facing errors use English."
            )
        _require(text, (marker,), f"{relative} tool-language boundary")

    wofi_text = "\n".join(
        (ROOT / f"sway/integrations/wofi/{name}").read_text()
        for name in ("select", "add", "remove")
    )
    _require(wofi_text, english_tool_markers, "committed Wofi tool surface")
    for forbidden in ("Keine Gruppe", "Neue Gruppe", "Zu Gruppe", "Aus Gruppe"):
        if forbidden in wofi_text:
            raise AssertionError(f"committed Wofi tool surface contains German UI: {forbidden}")

    sync = "uv sync --frozen --extra dev --extra cli --extra state --extra roba"
    external_clone = "git clone https://github.com/skaldos/dix-modules.git"
    for relative, text in docs.items():
        if text.index(sync) > text.index(external_clone):
            raise AssertionError(
                f"{relative} places external source in the DIX build input before initial sync"
            )

    config = (ROOT / "sway/integrations/sway/config").read_text()
    active_config_lines = [
        line for line in config.splitlines() if line and not line.startswith("#")
    ]
    for line in active_config_lines:
        if line not in sway_en or line not in sway_de:
            raise AssertionError(f"public Sway fragment drifted from committed config: {line}")

    requirements = (ROOT / "sway/requirements.txt").read_text()
    if requirements != "i3ipc==2.2.1\n":
        raise AssertionError("Sway dependency ownership is not exact")

    for relative in (
        Path("sway/integrations/bin/skaldos-sway-nav"),
        Path("sway/integrations/bin/skaldos-sway-json"),
        Path("sway/integrations/wofi/select"),
        Path("sway/integrations/wofi/add"),
        Path("sway/integrations/wofi/remove"),
    ):
        path = ROOT / relative
        if not path.is_file() or not path.stat().st_mode & 0o111:
            raise AssertionError(f"documented executable is missing or not executable: {relative}")


def main() -> int:
    verify()
    print("public documentation verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
