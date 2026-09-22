# Skaldos VisiData Workbench (V0)

A small interactive JSON editor for one **existing** ROBA Context key. It is
deliberately not a ROBA admin UI, a persistent profile editor, or a generic
command runner. The technical [`roba-key.toml`](templates/roba-key.toml)
access template names known get/set operations; the separate
[`profile.toml`](templates/profile.toml) gives the editable field a name. A
runtime binding selects the actual Context socket and key. The VisiData sheet
edits a detached draft; only explicit **Apply** writes.

## Install

Requires Python 3.12, `uv`, an installed `dix-roba-cli`, and an existing ROBA
Context with a **read+write capability socket**. `chafa` is optional for the
PNG display. The installer creates a dedicated VisiData 3.4 venv and a small
launcher; it does not change your DIX/ROBA runtime or source repos:

```sh
# Source your own central env first if DIX_BIN is customized.
# . "$HOME/.dix/env"
./visidata/integrations/install
```

`DIX_BIN` defaults to `~/.local/bin`;
`SKALDOS_WORKBENCH_VENV` defaults to
`${XDG_DATA_HOME:-~/.local/share}/skaldos/visidata-venv`. The installed
launcher references this checkout, so re-cloning it requires reinstalling.

Build/install `dix-roba-cli` using the DIX ROBA launcher instructions. Create
a Context and a capability socket with native `read` **and** `write` on that
Context (or the exact addressed Instance), then use the returned socket path.
Do **not** pass an owner token to this workbench. Example with placeholders:

**Capability scope is not key scope.** A socket granted `read`/`write` on
`context` can access other keys in that Context too; the workbench merely
binds itself to one named key. Protect the socket path and prefer a dedicated
test Context for experiments.

```sh
skaldos-workbench \
  --dix-roba-cli "$HOME/.local/bin/dix-roba-cli" \
  --locator unix:/absolute/context/sockets/rw.sock \
  --key profile \
  --logo dix
```

Use `--logo roba` to select the other current PNG. Both are copied from the
user-supplied `/cwd/pocs/gimp-mcp` assets:

| Asset | SHA-256 |
| --- | --- |
| `assets/dix.png` | `3f2c47cdbf876a51453344bf2e6693180116a684b4b88888591c42233793ad87` |
| `assets/roba.png` | `921757a4abb2e0e19ef647a2129b3396a29a82c436d4ee5d0eb333e0339c22b8` |

The PNG is shown on start, and **B** shows it again from VisiData. The exact
render command is `chafa --fill block -c full --scale 0.5 <PNG>`. On narrow
terminals or without `chafa`, a compact text label is used instead; editing
still works. No image is generated or downloaded by the installer.

## Keys

| Key | Effect |
| --- | --- |
| Enter | Drill into selected object/list |
| e | Edit selected existing scalar as JSON (`"text"`, `42`, `true`, `null`) |
| a | Apply the **whole** local key value via `dix-roba-cli data set` |
| B | Show the selected PNG again |
| q | Back/quit through VisiData |

The sheet name shows `*draft*` after a local edit. Apply failure keeps that
draft. V0 cannot insert/delete keys or list entries, replace containers
inline, compare-and-swap, or detect concurrent writers. **Apply replaces the
entire key** and may overwrite another writer's change to that key; unrelated
keys are not touched. No automatic re-read, no template-file write, and no
ROBA persistence/restart guarantee. Backend errors are summarized without
printing submitted JSON or credentials.

For tests: `uv run --no-project --with visidata==3.4 --with pytest==9.1.1
--python 3.12 python -m pytest -q tests/test_visidata_workbench_*.py` from
the repository root. Interactive visual acceptance requires a real terminal.
