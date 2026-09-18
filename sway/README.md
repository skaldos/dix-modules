# Skaldos Sway modules

This branch provides a small external DIX assembly for Sway navigation.

## Architecture

```text
skaldos/sway/core/ipc
├── focused_con_id
├── focus_direction
├── focus_con_id
├── live_con_ids
├── navigation_topology
└── command

skaldos/sway/nav/basic_nav
skaldos/sway/nav/windows_list_nav
skaldos/sway/nav/binding

skaldos/sway/nav/nav          # strict programmatic strategy facade
skaldos/sway/nav/basic        # Typer target
skaldos/sway/nav/windows_list # Typer target
skaldos/sway/nav/cli          # management CLI
```

`ipc.command` remains the generic low-level Sway boundary. `nav/binding` owns the domain-specific
rendering of `$dix_sway_nav`.

Two commands are intentionally delivered:

- `dix-sway-nav`: dependency-light, state-free keybinding hot path;
- `skaldos-sway-nav`: normal DIX/Typer management and test CLI.

Neither command reads group files, ROBA or navigation state. The active low-latency route is held
by Sway itself as one runtime variable.

## Source assembly

The canonical development assembly clones this repository as `modules/skaldos` below DIX:

```sh
git clone git@github.com:skaldos/dix.git ~/.dix/src/dix
cd ~/.dix/src/dix/modules
git clone --branch sway git@github.com:skaldos/dix-modules.git skaldos
```

Prepare the DIX environment and the one external runtime dependency:

```sh
cd ~/.dix/src/dix
uv sync --extra cli
uv pip install --python .venv/bin/python -r modules/skaldos/sway/requirements.txt
```

## Environment and installation

The installer creates `~/.dix/env` from the provided template when it does not exist:

```sh
~/.dix/src/dix/modules/skaldos/sway/nav/integrations/install
```

To use different locations, create or edit `~/.dix/env` before installation. Relevant values are:

```sh
export DIX_SOURCE_ROOT="$HOME/.dix/src/dix"
export SKALDOS_SWAY_ROOT="$DIX_SOURCE_ROOT/modules/skaldos/sway"
export DIX_VENV="$DIX_SOURCE_ROOT/.venv"
export DIX_LAUNCHERS="${XDG_DATA_HOME:-$HOME/.local/share}/dix/launchers"
export DIX_BIN="$HOME/.local/bin"
```

A different environment file can be selected for installation and every installed command:

```sh
DIX_ENV="$HOME/path/to/dix.env" \
  "$SKALDOS_SWAY_ROOT/nav/integrations/install"
```

The installer is repeatable and produces:

```text
$DIX_BIN/dix-sway-nav
$DIX_BIN/skaldos-sway-nav
$DIX_LAUNCHERS/dix-sway-nav.py
$DIX_LAUNCHERS/skaldos-sway-nav.py
```

## Sway configuration

Copy or include `sway/nav/integrations/sway/config` and replace `/home/YOU` with the real home
path. The relevant contract is:

```sway
set $dix_sway_nav basic
bindsym $mod+h exec --no-startup-id $dix_bin/dix-sway-nav left $$dix_sway_nav
bindsym $mod+j exec --no-startup-id $dix_bin/dix-sway-nav down $$dix_sway_nav
bindsym $mod+k exec --no-startup-id $dix_bin/dix-sway-nav up $$dix_sway_nav
bindsym $mod+l exec --no-startup-id $dix_bin/dix-sway-nav right $$dix_sway_nav
```

The doubled dollar sign is essential: Sway expands the route when the binding runs, not while the
configuration is loaded.

## Management CLI

```sh
skaldos-sway-nav basic set
skaldos-sway-nav basic left

skaldos-sway-nav windows-list set --ids 23 --ids 42
skaldos-sway-nav windows-list right --ids 23 --ids 42
```

`set` changes the single Sway runtime route. Direction commands execute their strategy directly
and are useful for manual testing.

## Direct hot path

```sh
dix-sway-nav left basic
dix-sway-nav right windows-list 23 42
```

Invalid strategy or window IDs fall back best effort to one native step in the requested
direction. The normal DIX applications and the management CLI remain strict and do not inherit
this desktop fallback policy.

## Development checks

```sh
cd ~/.dix/src/dix/modules/skaldos
DIX_REPOSITORY=~/.dix/src/dix ~/.dix/src/dix/.venv/bin/python -m pytest -q
~/.dix/src/dix/.venv/bin/python -W error -m compileall -f -q sway tests
```
