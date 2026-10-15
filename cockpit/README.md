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
