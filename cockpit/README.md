# DIX Cockpit

DIX Cockpit is one isolated, privileged terminal runtime owned by a name. Each session combines:

- its own ROBA daemon and native Control capability;
- one session on a Cockpit-only tmux server;
- an isolated owner Zsh with private startup files and history;
- a separate DIX or ROBA logo/status pane.

It does not use DIX Control, a daemon catalog, VisiData, the host tmux server, or host Zsh files for
its main lifecycle. The retained catalog/provider code is legacy and is not involved in
`dix-cockpit`.

## Requirements and installation

DIX must provide `dix/state`, `dix/cli`, `dix/norn`, and `dix/roba`, and its environment must expose
`DIX_SOURCE_ROOT`, `DIX_VENV`, `DIX_LAUNCHERS`, and `DIX_BIN`. ROBA must already be available in
that Python environment. The host needs tmux and Zsh. Chafa and Wayland/X11 clipboard tools are
optional.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; this is the default
./cockpit/integrations/install
```

The installer is repeatable. It builds only the main, owner-shell, and status launchers, installs
namespaced wrappers, private tmux/Zsh configs, and both reviewed logos. It neither edits the DIX
environment nor reads or overwrites host tmux/Zsh configuration. It assembles an explicit private
runtime module containing only the three runtime applications and their four Cockpit
compositions. The launchers therefore neither load nor require the separately retained VisiData
module.

Optional process-local overrides:

```sh
export DIX_COCKPIT_RUNTIME_ROOT="${XDG_RUNTIME_DIR:-/tmp}/dix-cockpit"
export DIX_COCKPIT_STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/skaldos/cockpit"
export DIX_COCKPIT_TMUX_CONFIG="$DIX_LAUNCHERS/cockpit/tmux.conf"
export DIX_COCKPIT_ZSH_CONFIG="$DIX_LAUNCHERS/cockpit/zsh/.zshrc"
export DIX_COCKPIT_ASSET_ROOT="$DIX_LAUNCHERS/cockpit/assets"
```

Keep `DIX_COCKPIT_RUNTIME_ROOT` short: Unix-domain socket paths have a strict platform limit, which
Cockpit validates before creating anything.

## Commands

```sh
dix-cockpit start  [--session NAME] [--logo dix|roba]
dix-cockpit attach [--session NAME]
dix-cockpit status [--session NAME]
dix-cockpit stop   [--session NAME]
dix-cockpit reset  [--session NAME] [--logo dix|roba]
```

Session and logo default to `dix`.

- `start` creates or reuses the complete runtime and attaches.
- `attach` and `status` never create or repair resources. Status is JSON and exits non-zero unless
  the complete runtime is healthy.
- `stop` first stops only the proven-owned ROBA daemon, removes volatile capability data, and then
  stops the owned tmux session. The tmux server is killed only after its final session. Logs and
  shell history remain.
- `reset` performs an ownership-checked stop, starts a fresh runtime with a new capability, and
  attaches.
- Detach or client loss stops nothing. `stop` and `reset` from inside the target session are
  rejected; detach first.

A running owned daemon with a missing tmux session is rebuilt by `start`. A live tmux session with
an absent or invalid daemon is not silently repaired; use `reset`. Foreign daemons, malformed
owner artifacts, and foreign tmux sessions are never adopted or stopped.

A failed ROBA status request is treated as safely absent only when both expected runtime endpoints
are absent. If either endpoint still exists, status reports an uncertain runtime and every
lifecycle mutation fails closed. The dedicated tmux server and every Cockpit session carry
separate non-secret ownership markers; a reachable unmarked server is never adopted, even when the
requested session does not exist.

## Owner shell and tmux

The first window contains the owner Zsh and a separate non-blocking logo/status pane. New `|` and
`-` splits invoke the same owner-shell entry again. Only that shell child loads the private capability into its process environment and receives `ROBA_CONTROL_TOKEN`, `ROBA_DAEMON=id:default`, and
`ROBA_CONTROL=id:default`. tmux environment, options, pane titles, status, argv, and documentation
remain secret-free.

The owner shell has its own `ZDOTDIR`, history, completion for `dix-cockpit`, `dix-roba-cli`, and
`roba-ctl`, and a visible prompt containing both `cockpit` and the concrete session name. Existing
navigation, resize, vi copy mode, reload, and clipboard adapters remain available. The owner
artifact and Zsh files use mode `0600`; private directories use `0700`.

Useful checks inside the owner shell:

```sh
dix-roba-cli daemon status
roba-ctl ctx list
```

The status pane renders the selected reviewed PNG with Chafa when available and falls back to text.
A real visual terminal review remains separate from automated verification.

## Optional master UI

The master UI is an explicit optional layer on top of the privileged runtime. Install the base
runtime first, then the UI:

```sh
./cockpit/integrations/install
./cockpit/integrations/install-ui

dix-cockpit-ui start --session dix --logo dix
```

The second installer adds VisiData 3.4 and builds a separate static allowlisted source projection
with `dix-cockpit-ui` and the internal `dix-cockpit-master-workbench` helper. Repeating it replaces
that private projection and removes stale files. It does not broaden or replace the base runtime
installer; the three runtime launchers remain VisiData-free.

`dix-cockpit-ui start` uses the existing Cockpit lifecycle, completes the existing `control`
window and attaches. The window contains the logo/non-secret status, the owner shell and the
largest pane for the generic ROBA Loom workbench. Every pane has a visible title. A repeated start
focuses the running workbench. If that process exited, its pane and error remain visible; the next
explicit UI start respawns that same role instead of creating a duplicate. Detach leaves all
processes alive. Continue to use `dix-cockpit attach|status|stop|reset` for lifecycle operations;
the UI intentionally duplicates none of them.

The master helper validates the live owner artifact inside its own process and creates the Loom
connection there. Its Control token is never passed in argv, a seed file, tmux environment,
options, role metadata or titles. The token is intentionally visible and editable inside this
personal owner workbench. Enter only inspects the selected ObjectReference and opens a local
draft. Space is the sole provider execution path and keeps the existing confirmation. Provider
errors preserve the workbench session.

tmux keeps the isolated key surface described above: `C-a` (or `C-b`) is the prefix, `h/j/k/l`
navigates panes, `C-h`/`C-l` changes windows, `H/J/K/L` resizes, and `Escape` enters vi copy mode.
The configured copy/paste adapters prefer the system clipboard and fall back to the private tmux
buffer. No locator catalog, external target window, file import/export, save, sync or runner is
part of this UI.

## Optional local TOML value workbench

The local TOML workbench is deliberately separate from the privileged runtime installer. It needs
Python 3.12, `uv`, VisiData 3.4, this complete `dix-modules` checkout, and the same central DIX
environment. It does not need a running Cockpit session, ROBA, DIX Control, a catalog, or a Loom
provider.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; this is the default
./cockpit/integrations/install-workbench

dix-cockpit-toml-workbench --file ./value.toml --logo dix
# or: --logo roba
```

The optional installer creates a fresh private source projection containing only the TOML-file
reader, the local value workbench, the one Cockpit application, and both logos. It installs only
`dix-cockpit-toml-workbench`. Repeating it removes stale files from that projection. It does not
change `cockpit/integrations/install`, its three privileged launchers, the tmux layout, or the
owner shell.

The explicit path is interpreted relative to the process working directory unless it is absolute.
The source is read exactly once as UTF-8 TOML. The workbench receives a detached native value;
path metadata is not injected into that value. The source and its directory are never written.
Closing the process discards the draft and its local register. There is no save, reload, recovery,
sync, import/export, or provider execution in this command.

### Local workbench keys

| Key | Effect |
| --- | --- |
| Enter | Drill into the selected mapping or list; never execute externally |
| e | Replace the selected scalar with exactly one TOML literal |
| a | Add a mapping entry or append a TOML value to the current list |
| i | Insert a TOML value before the selected list item |
| r | Rename the selected mapping key without overwriting another key |
| d | Confirm and delete the selected mapping or list entry |
| y | Deep-copy the selected complete subtree into the session-local register |
| p | Replace the selected subtree with a deep copy of the register |
| A | Add the register to the current mapping or append it to the current list |
| I | Insert the register before the selected list item |
| B | Show the selected DIX/ROBA logo again |
| q | Return/quit through VisiData; all local changes are discarded on process exit |

The sheet title always shows `clean` or `DIRTY` and whether the local register is `empty` or `set`.
A fixed two-part header shows branding and source file, the dirty/register state read live from the
draft, and the current breadcrumb from `value` through the visible mapping key or list index. It is
not a selectable data row.
Invalid TOML, missing paths, wrong container types, invalid indices, key collisions, an empty
register, and cancelled deletion leave both draft and register unchanged. Native TOML dates,
times, datetimes, special floats, and nested mappings/lists remain native values.
