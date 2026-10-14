# DIX Cockpit

DIX Cockpit is an isolated tmux workspace for several explicit ROBA daemon roots. It reuses the
existing provider-neutral VisiData Loom workbench in each connection window. The Cockpit is an
orchestrator, not a daemon manager: starting or stopping the Cockpit never starts or stops a ROBA
daemon.

## Requirements and installation

- DIX with `dix/state`, `dix/cli`, `dix/norn` and `dix/roba`;
- this repository with the sibling `visidata` and `cockpit` module roots;
- `uv`, Python 3.12+, tmux and the normal central DIX environment;
- VisiData 3.4 (installed into `DIX_VENV` by the installer);
- optional `chafa`, `wl-copy`/`wl-paste`, or `xclip`.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; this is the default
./cockpit/integrations/install
```

The installer builds three normal DIX launchers, installs `dix-cockpit` and its internal window
helpers in `DIX_BIN`, and copies the Cockpit-owned tmux config below `DIX_LAUNCHERS/cockpit`.
It creates the default catalog only if it does not exist. It does not edit the central DIX env,
source a host tmux config, or overwrite an existing catalog.

Useful optional overrides are:

```sh
export DIX_COCKPIT_CATALOG="$HOME/.config/skaldos/cockpit/daemons.toml"
export DIX_COCKPIT_RUNTIME_ROOT="${XDG_RUNTIME_DIR:-/tmp}/dix-cockpit"
export DIX_COCKPIT_TMUX_CONFIG="$DIX_LAUNCHERS/cockpit/tmux.conf"
export SKALDOS_VISIDATA_ROOT="$HOME/.dix/src/dix-modules/visidata"
```

Keep `DIX_COCKPIT_RUNTIME_ROOT` short. Unix-domain sockets have a small platform path limit, which
Cockpit checks before invoking tmux.

## Explicit daemon catalog

```toml
[daemons.default]
daemon_id = "default"
runtime_root = "~/.roba/runtime"
logs_root = "~/.roba/logs"
timeout = 5.0

[daemons.lab]
daemon_id = "lab"
runtime_root = "/run/user/1000/roba-lab"
logs_root = "~/.local/state/roba-lab/logs"
```

The table name is the stable local catalog/window identity. `daemon_id` is the provider identity.
Relative roots are resolved against the catalog directory; `~` is expanded. Unknown fields,
duplicates, empty values and invalid timeouts fail visibly. The catalog is not discovery and must
never contain tokens.

## Commands and lifecycle

```sh
dix-cockpit start  [--session NAME] [--catalog PATH] [--logo dix|roba]
dix-cockpit attach [--session NAME]
dix-cockpit status [--session NAME]
dix-cockpit stop   [--session NAME]
```

The session and logo default to `dix`. `start` creates or focuses the dedicated Cockpit tmux
session and attaches. `attach` and `status` never create it. `stop` removes only the named Cockpit
session and cleans the empty isolated tmux server; it never stops a catalog daemon.

The Control window keeps stopped and failed targets visible. Reload the sheet with the normal
VisiData reload command. Enter opens or focuses one stable connection window without a Loom
effect. The connection window uses the unchanged Loom workbench controls:

- **Enter**: inspect/open/drill only;
- **Space**: explicitly confirm and execute the selected Loom reference;
- `e` / `r`: edit a scalar or replace a JSON-compatible draft subtree;
- `B`: show the selected workbench branding where available.

A stopped target opens with the basic connection and therefore offers an explicit Loom `start`.
A running target is resolved through DIX Control in-process. Broken Control credentials are shown
as an error; they are never replaced by invented or weaker credentials.

## Isolated tmux and clipboard

Every tmux call uses the same dedicated `-S` socket. Only server creation loads the Cockpit config.
The host server, host config and plugins are not used. Cockpit provides `C-a` (plus nested `C-b`),
vi copy mode, h/j/k/l pane navigation, C-h/C-l window navigation, H/J/K/L resizing, `|` and `-`
splits, Escape copy mode and its own status/header area.

Copy/paste uses Wayland first, then Xclip, then the isolated tmux buffer. The helpers pass bytes
through stdin/stdout and never interpolate clipboard contents as shell commands. The fallback is
reported in the terminal.

## Secret boundary

The local connection workbench deliberately shows complete materialized values, including tokens,
for this pressure-test stage. Those values stay in-process. Tokens are never copied into process
arguments, tmux names/options, header/status text, logs, documentation or catalog files. A real
terminal/visual review remains separate from automated verification.
