# Direct VisiData Loom Workbench (V0)

This module is a provider-neutral VisiData client for the closed Loom contract:

```python
execute(value, object_id=None)
# -> [{"object_id": str, "description": str, "value": object}, ...]
```

The delivered DIX application binds that generic workbench directly and in-process to
`dix/roba/loom`. It does **not** invoke `dix-roba-cli`, select a provider from edited data, or run
commands/imports named by a seed. `dix-roba-workbench` always requires an explicit JSON seed.

## Install

Requirements are Python 3.12, `uv`, a DIX environment with the ROBA extra, and the current DIX and
this `dix-modules` checkout. The central environment defaults to `~/.dix/env` and must define:

```sh
DIX_SOURCE_ROOT=...  # DIX source checkout
DIX_VENV=...         # DIX venv with ROBA support
DIX_LAUNCHERS=...
DIX_BIN=...
```

Install VisiData 3.4 into that DIX venv and build the normal `python_cli` launcher:

```sh
. "$HOME/.dix/env"
./visidata/integrations/install
```

The installer creates only `dix-roba-workbench` and removes an old installed
`$DIX_BIN/skaldos-workbench` wrapper if present. It does not delete unknown user files or old venvs.
The DIX launcher currently also loads `dix/cli` because the complete `dix/roba` module declares
its own CLI application; the workbench provider path itself never calls that CLI.

## Seed and start

A daemon configuration is the smallest useful ROBA Loom seed. Use isolated roots for experiments:

```json
{
  "daemon_id": "workbench-test",
  "runtime_root": "/tmp/workbench-test/runtime",
  "logs_root": "/tmp/workbench-test/logs",
  "timeout": 5.0
}
```

```sh
dix-roba-workbench --seed ./seed.json --logo dix
# or: --logo roba
# local pressure tests only: --no-confirm
```

Invalid or unreadable JSON fails before VisiData and before any provider call. Both shipped PNGs
retain their documented SHA-256 values:

| Asset | SHA-256 |
| --- | --- |
| `assets/dix.png` | `3f2c47cdbf876a51453344bf2e6693180116a684b4b88888591c42233793ad87` |
| `assets/roba.png` | `921757a4abb2e0e19ef647a2129b3396a29a82c436d4ee5d0eb333e0339c22b8` |

Branding uses `chafa --fill block -c full --scale 0.5`. Missing Chafa, redirected I/O, or a small
terminal never blocks the workbench.

## Keys and effects

Reference sheet:

| Key | Effect |
| --- | --- |
| Enter | Inspect the selected complete reference as a detached local draft; never execute |
| Shift+Enter | Show `object_id` and value, ask for confirmation, then execute exactly once |
| B | Show the selected logo again |
| q | Return/quit through VisiData |

Draft sheet:

| Key | Effect |
| --- | --- |
| Enter | Drill into a mapping/list; never execute |
| e | Replace a selected JSON-compatible scalar locally |
| r | Replace a complete JSON-compatible subtree locally |
| Shift+Enter | Show and confirm the complete draft, then execute exactly once |
| q | Return to the previous sheet |

**Every reference may represent an external effect.** The generic client deliberately does not
classify names such as `read`, `write`, `start`, or `delete`. Enter/edit/sheet navigation/exit are
local only; **Shift+Enter** is the only provider call after initial seed resolution. It confirms by
default. The explicit `--no-confirm` option skips that prompt and is intended only for controlled
local pressure tests. Cancel performs no call. Provider exceptions remain visible and retain the
draft. An empty result is successful and opens an empty reference sheet. Every reference sheet
owns the complete reference values it displayed, so returning to an older sheet cannot resolve its
rows against a newer provider result. History is navigation state, not undo or rollback of external
effects.

Terminal input normally does not distinguish Shift+Enter from Enter. This workbench therefore
binds execution to a dedicated CSI-u sequence and leaves both normal Enter and LF untouched. For
Alacritty, map the physical key explicitly:

```toml
[[keyboard.bindings]]
key = "Enter"
mods = "Shift"
chars = "\u001b[13;2u"
```

Without such a terminal mapping Shift+Enter remains indistinguishable from Enter and does not
execute. The workbench never turns plain Enter or LF into execution.

The local interactive sheet intentionally displays complete values, including tokens and socket
capabilities returned by ROBA. Run it only in a trusted terminal; protect screenshots, scrollback,
and recordings. There is no automatic redaction, clipboard/export policy, credential recovery,
session persistence, CAS, multi-writer conflict handling, or rollback. Native non-JSON values are
inspectable but cannot be lossily rewritten by the V0 editor.

## Tests

From the repository root, with the pinned ROBA source available:

```sh
uv run --no-project --with /cwd/repos/roba --with visidata==3.4 \
  --with pytest==9.1.1 --python 3.12 \
  python -m pytest -q tests/test_visidata_*.py
```

The real test uses a temporary daemon and temporary state only. Interactive visual acceptance still
requires a real terminal.
