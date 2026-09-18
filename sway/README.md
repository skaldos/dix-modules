# `skaldos/sway`

Topology-aware Sway window-group navigation assembled with DIX and coordinated through ROBA.

[Deutsch](README.de.md) · [Repository overview](../README.md) ·
[DIX](https://github.com/skaldos/dix) · [ROBA](https://github.com/skaldos/roba)

> **Public Alpha:** this module is already useful in a real Sway workflow, but setup and source
> contracts may still change. It is delivered as source, not as a Python package.

Documentation is available in English and German. Shipped command names, prompts, and
machine-facing errors use English.

## What it does

`skaldos/sway` lets a normal Sway directional binding operate either natively or against one
selected group of window container IDs:

```text
Sway IPC
+ ROBA coordination state
+ DIX compositions/applications
+ fixed low-latency keybindings
+= topology-aware window-group navigation
```

Sway remains the direction authority. Group navigation first performs the native
`focus left|right|up|down` command. A direct allowed hit is accepted immediately. If Sway enters a
stacked or tabbed branch whose visible leaf is not in the active group, the module uses a minimal
Sway topology to select an allowed live leaf inside that entered branch. It does not replace Sway
with a geometry-based window manager.

## Responsibility map

The system deliberately keeps different state under different owners:

| Owner | Data or behavior |
| --- | --- |
| Sway | Live tree, focus, container IDs, native direction semantics. |
| DIX | Explicit loading and assembly of compositions and applications. |
| ROBA | Ephemeral shared coordination: group names and active group name. |
| Group application | Private JSON mapping of group names to Sway `con_id` values. |
| Navigation projections | One line of active live member IDs and one `basic`/`group` route value. |
| Theme catalog | Complete user-owned TOML definitions below the configured theme directory. |
| Active theme projection | ID last applied successfully by this application; not live Sway state. |
| User | Process lifecycle, local paths, filesystem permissions, and keybindings. |

ROBA **persists nothing**. The private JSON and the two projection files are ordinary local files
owned by this module's configured workflow; they are not ROBA persistence. Sway container IDs are
runtime values and can become stale after applications or Sway restart.

## Requirements

- Linux with Sway and a working `SWAYSOCK`;
- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/);
- Git;
- Wofi only if the optional chooser scripts are used.

The module owns exactly one direct Sway dependency in [`requirements.txt`](requirements.txt):
`i3ipc==2.2.1`. DIX intentionally does not own it.

## 1. Clone the source layout

Start in an empty directory:

```sh
mkdir -p skaldos-sway-showcase
cd skaldos-sway-showcase
git clone https://github.com/skaldos/roba.git roba
git clone https://github.com/skaldos/dix.git dix

export SKALDOS_WORKSPACE=$PWD
export DIX_SOURCE_ROOT=$SKALDOS_WORKSPACE/dix
```

Do not place the external checkout below `dix/modules` before the initial DIX sync. Directories
present there are inputs to a locally built DIX distribution. Preparing the committed DIX source
first keeps that distribution limited to DIX-owned modules; the external checkout remains a source
consumer added afterwards.

## 2. Prepare the DIX environment

DIX already points to the sibling `../roba` source in this layout. Sync its declared extras, then
install the Sway-owned requirements into the same environment:

```sh
cd "$DIX_SOURCE_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba

git clone https://github.com/skaldos/dix-modules.git "$DIX_SOURCE_ROOT/modules/skaldos"
export SWAY_ROOT=$DIX_SOURCE_ROOT/modules/skaldos/sway

uv pip install --python "$DIX_SOURCE_ROOT/.venv/bin/python" -r "$SWAY_ROOT/requirements.txt"
```

The final dependency-install command is intentionally visible. No import hook silently installs
`i3ipc`.

The resulting shape is intentional:

```text
$SKALDOS_WORKSPACE/
├── roba/
└── dix/
    └── modules/
        ├── dix/{cli,state,roba}
        └── skaldos/sway
```

There is no Git-submodule, package-manager, or discovery relationship between the repositories.
DIX receives `skaldos/sway` as an explicit source path and module ID.

## 3. Create one central DIX environment

Install the commented XDG-oriented template once. This is the only file that local commands source:

```sh
mkdir -p "$HOME/.dix"
cp "$SWAY_ROOT/integrations/env" "$HOME/.dix/env"
${EDITOR:-vi} "$HOME/.dix/env"
```

The defaults use `XDG_RUNTIME_DIR`, `XDG_STATE_HOME`, and `XDG_DATA_HOME` where appropriate.
Override values in this file for a custom tree such as `~/.dix`; do not duplicate them in Sway.
`SKALDOS_SWAY_GROUP_STATE_FILE`, `SKALDOS_SWAY_ACTIVE_MEMBERS_FILE`,
`SKALDOS_SWAY_NAVIGATION_TARGET_FILE`, `SKALDOS_SWAY_THEME_DIR`,
`SKALDOS_SWAY_THEMED_GROUP_DIR`, and `SKALDOS_SWAY_ACTIVE_THEME_FILE` remain separate boundaries.
Theme and themed-group TOMLs are persistent user configuration; `active-theme` is only a
replaceable projection of the ID last applied successfully by this application.

Treat `groups.json` as local user state. The projection files are replaceable outputs and must not
be edited into malformed values.

## 4. Build and install the local launchers and commands

The management entry needs a running ROBA daemon, the DIX control registry, and a managed context.
The general integration installer builds the committed Typer application and installs management,
theme, and Wofi commands below `DIX_BIN`. Navigation is deliberately separate; its own installer
copies only the direct low-latency launcher and `dix-sway-nav` wrapper:

```sh
"$SWAY_ROOT/integrations/install"
"$SWAY_ROOT/integrations/navigation/install"
export PATH=$HOME/.local/bin:$PATH
dix-roba --help
skaldos-sway --help
```

The resulting `dix-roba`, full Typer-based `skaldos-sway`, direct `skaldos-sway-json`,
low-latency `dix-sway-nav`, and Wofi commands all source `~/.dix/env`. Their Python launchers
live together below `DIX_LAUNCHERS`, but only the explicit navigation installer owns
`dix-sway-nav`. The general installer neither installs nor invokes it.

The installer also copies the complete `dix.toml` and `roba.toml` examples plus their PNG
wallpapers into `SKALDOS_SWAY_THEME_DIR` when they do not exist. Re-running it never overwrites
any of these user-owned targets.

## 5. Configure ROBA, start it, and create `skaldos-sway`

Without overrides DIX itself keeps the proven daemon ID `default`, runtime root `~/.roba/runtime`,
and logs root `~/.roba/logs`. The installed environment template instead supplies XDG-oriented
`DIX_ROBA_RUNTIME_ROOT` and `DIX_ROBA_LOGS_ROOT` values to every local command:

```sh
dix-roba managed start
dix-roba control create_context \
  --context_id skaldos-sway
dix-roba daemon status
```

`managed start` starts ROBA and bootstraps the DIX control context. `create_context` then creates
the module context and its manager socket. These commands print capability-bearing result data;
do not paste tokens into documentation, logs, or tickets.

Set the two values in `~/.dix/env` to use arbitrary absolute user-owned paths:

```sh
export DIX_ROBA_RUNTIME_ROOT=/absolute/path/to/roba-runtime
export DIX_ROBA_LOGS_ROOT=/absolute/path/to/roba-logs
```

Every installed command reads the same file. Named Typer parameters such as `--runtime_root` and
`--logs_root` still override it for one call. Do not use an unexpanded literal `~` in custom paths.

Do not run `create_context` repeatedly against an already existing context. A duplicate is a
visible error, not an attach operation.

## 6. Inspect the transparent wrappers

The two explicit installers placed their respective wrappers below `DIX_BIN`. They contain only
this boundary:

```sh
cat "$HOME/.local/bin/dix-sway-nav"
cat "$HOME/.local/bin/skaldos-sway-json"
```

The wrappers never start ROBA. `skaldos-sway-json` is the broad DIX/ROBA management path;
`dix-sway-nav` is the direct dependency-light navigation path.

## 7. Manage groups

Run these commands inside a real Sway session with the three state variables exported.

Create and list a group:

```sh
skaldos-sway-json create work
skaldos-sway-json list-lines
```

Focus a window, add it, and inspect the groups containing the focused window:

```sh
skaldos-sway-json add work
skaldos-sway-json memberships-lines
```

Focus each additional window and repeat `add work`. A window may belong to multiple groups.

Activate a group and inspect the active name:

```sh
skaldos-sway-json select work
skaldos-sway-json current
```

Remove the currently focused window from a group:

```sh
skaldos-sway-json remove work
```

Return routing to native/basic navigation without deleting the private group:

```sh
skaldos-sway-json deactivate
```

`create`, `add`, `remove`, `select`, and `deactivate` are explicit mutations. `list-lines`,
`memberships-lines`, and `current` are line-oriented chooser/read outputs.

## 8. Manage complete themes

The full Typer application exposes the separately composed theme catalog and Sway IPC functions:

```sh
skaldos-sway theme list
skaldos-sway theme list_lines
skaldos-sway theme show --theme dix
skaldos-sway theme apply --theme dix
skaldos-sway theme current
skaldos-sway theme create --theme personal
```

All parameters are named options. Override the persistent catalog or the active projection for one
call with `--theme_dir /absolute/themes` and
`--active_theme_file /absolute/state/active-theme`. Central defaults remain
`SKALDOS_SWAY_THEME_DIR` and `SKALDOS_SWAY_ACTIVE_THEME_FILE` in `~/.dix/env`.

Every theme is complete: all effective Sway client color classes are required. A theme may omit
the output background, use one solid color, or use an image for `output *`:

```toml
[background]
type = "image"
file = "wallpapers/example.png"
mode = "fill"
fallback_color = "#10080E"
```

Relative images resolve against the theme file. `theme current` reports only the ID last applied
successfully by this application. It does not inspect Sway live, and a marker surviving a Sway
restart does not prove that the theme was reapplied in the new session.

### Persistent themed groups

A themed group is one explicit persistent assignment between an existing group name and one
complete theme. Create one TOML per assignment below `SKALDOS_SWAY_THEMED_GROUP_DIR`, whose default
is `$SKALDOS_SWAY_CONFIG_ROOT/themed-groups`:

```toml
# ~/.config/skaldos/sway/themed-groups/dix-dev.toml
group = "DIX development"
theme = "dix"
```

The filename stem is a definition ID and must match `[a-z0-9][a-z0-9_-]*`. It is not the group
name: a normalized, non-empty group such as `DIX development` may intentionally differ. A named
`--themed_group_dir` option overrides composition configuration, which overrides
`SKALDOS_SWAY_THEMED_GROUP_DIR`. Theme lookup independently follows `--theme_dir`, application
composition configuration, and `SKALDOS_SWAY_THEME_DIR`.

Inspect, explicitly bootstrap, and then select the assignment:

```sh
skaldos-sway themed_group list
skaldos-sway themed_group load
skaldos-sway themed_group select --group "DIX development"
```

`list` validates the complete assignment catalog but does not touch groups, themes, ROBA, or Sway.
`load` first validates every assignment and every referenced theme. Only after that preflight does
it deactivate an active currently declared group, clear every already existing declared group, and
create each missing declared group. Clearing intentionally discards all old Sway `con_id` member
bindings. Groups outside the current catalog remain untouched, including foreign groups and groups
whose old definition was removed; without a persistent ownership registry they cannot be safely
distinguished.

The group mutations after preflight are not transactional. If one fails, run `load` again after
fixing the cause. `select` preflights its theme, then selects the group, then applies the theme. If
theme IPC fails after selection, the selected group stays active and no cross-application rollback
is attempted. This slice does not add workspace automation, a Wofi adapter, or a new low-latency
launcher; those remain separate integrations.

## 9. Test navigation directly

The low-latency command is stateless. Select the strategy explicitly after the direction:

```sh
dix-sway-nav right basic
dix-sway-nav left windows-list 23 3542 1
dix-sway-nav up windows-list
```

`windows-list` receives positive unique Sway window `con_id` values. An empty list is a successful
no-op. Every success emits one compact JSON envelope with `requested`, `executed`, `fallback`, and
`result`. After a valid direction, malformed strategy arguments or a failing `windows-list` attempt
exactly one native `basic` fallback. The direct process reads no group projection or route file and
intentionally imports no Typer, Click, ROBA, HTTPX, or Pydantic.

## 10. Optional Wofi commands

The installer provides four direct commands:

```sh
skaldos-sway-wofi-select
skaldos-sway-wofi-add
skaldos-sway-wofi-remove
skaldos-sway-wofi-theme
```

Their source adapters remain under `integrations/wofi/select`, `integrations/wofi/add`,
`integrations/wofi/remove`, and `integrations/wofi/theme`.

The existing-entry menus invoke Wofi with `--no-custom-entry`. Pressing Enter on the initially
highlighted row therefore commits that row without requiring a cursor movement. Only the separate
"new group" dialog accepts free text.

The theme chooser reads the line-oriented `theme list_lines` application function and applies the
selected catalog entry through `theme apply`. It performs no independent filesystem discovery and
does not offer free theme-name input.

The action rows are `[No active group]` and `[+ New group]`. The add and remove prompts are
`Add window to group` and `Remove window from group`; free group-name input uses
`New group name`.

Override `SKALDOS_SWAY_MANAGEMENT`, `SKALDOS_SWAY_THEME_MANAGEMENT`, `SKALDOS_SWAY_WOFI`, or
`SKALDOS_SWAY_WOFI_NAME` only when you intentionally own the replacement command. These variables
are shell command boundaries, not a DIX API.

## 11. Add the Sway bindings

Management/Wofi bindings and navigation bindings have separate ownership. Copy both maintained
fragments, [`integrations/sway/config`](integrations/sway/config) and
[`integrations/navigation/sway/config`](integrations/navigation/sway/config), into the Sway
configuration and replace `/home/YOU` with the real absolute home directory:

```text
set $skaldos_home /home/YOU
set $skaldos_bin $skaldos_home/.local/bin

bindsym $mod+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-select
bindsym $mod+Shift+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-add
bindsym $mod+Ctrl+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-remove
bindsym $mod+t exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-theme

set $dix_home /home/YOU
set $dix_bin $dix_home/.local/bin

bindsym $mod+h exec --no-startup-id $dix_bin/dix-sway-nav left basic
bindsym $mod+j exec --no-startup-id $dix_bin/dix-sway-nav down basic
bindsym $mod+k exec --no-startup-id $dix_bin/dix-sway-nav up basic
bindsym $mod+l exec --no-startup-id $dix_bin/dix-sway-nav right basic
```

Sway receives no DIX-specific environment. Every command loads the current values from
`~/.dix/env`, so changing that file affects the next invocation without reloading Sway.

Choose bindings that do not conflict with your configuration. Reload and perform a basic smoke
test:

```sh
swaymsg reload
skaldos-sway-json list-lines
dix-sway-nav right basic
```

The final command moves focus. Once a group has live members, select it and test the fixed bindings.

## Shutdown and restart

Stop the default daemon explicitly:

```sh
dix-roba daemon stop
```

All ROBA contexts and coordination state disappear. The private JSON and projection files remain
because they are separate local files, not ROBA state.

After a ROBA-only restart:

```sh
dix-roba managed start
dix-roba control create_context \
  --context_id skaldos-sway
skaldos-sway-json deactivate
skaldos-sway-json select work
```

The final two calls republish coordination and projections from the private group state. After a
Sway restart, stored `con_id` values may be stale; rebuild membership against the new live windows
instead of treating those IDs as persistent identities.

## Troubleshooting

### `composition definition is not loaded: dix/cli/typer`

An old or incomplete launcher loaded `dix/roba` without first loading `dix/state` and `dix/cli`.
Rebuild and reinstall `dix-roba` from the committed DIX spec shown above. Do not hand-remove its
module list.

### Manager socket is missing

A typical failure names a missing socket below
`$DIX_ROBA_RUNTIME_ROOT/daemons/default/contexts/dix.control/sockets/` or the default
`~/.roba/runtime/...` tree. Confirm that `managed start` succeeded, then create `skaldos-sway`
exactly once. If the daemon was restarted, its old sockets and contexts no longer exist and both
steps must be repeated.

### A socket path contains the wrong `~` or becomes relative

Shells do not expand `~` inside arbitrary quoted variables or generated strings. Use absolute
paths in `DIX_ROBA_RUNTIME_ROOT` and `DIX_ROBA_LOGS_ROOT`, and ensure the process launching a
terminal, Wofi, or a Sway binding provides both values. Partial custom-root configuration points
different processes at different daemons and is unsupported.

### ROBA is running, but `skaldos-sway` is missing

Daemon status alone is insufficient. Run the `control create_context --context_id skaldos-sway`
command. If it reports that the context already exists, do not create a second one; inspect the
manager-socket path and ensure every command uses the same daemon configuration.

### Navigation falls back to basic

Read the one-line primary error on stderr. The direct command does not read the legacy
`navigation-target` or `active-members` projections. Pass `basic` explicitly, or pass
`windows-list` followed only by positive unique window `con_id` values. A successful fallback is
reported in the JSON envelope with `executed="basic"` and `fallback=true`.

### Sway or i3ipc cannot connect

Verify all of the following from the same environment:

```sh
printf '%s\n' "$SWAYSOCK"
swaymsg -t get_tree >/dev/null
"$DIX_SOURCE_ROOT/.venv/bin/python" -c 'import i3ipc; print(i3ipc.__version__)'
```

If the import fails, repeat the explicit requirements installation. If `swaymsg` fails, run the
command inside the correct Sway session; the module does not create or discover a display server.

## Known alpha limits

- No daemon or context is started automatically.
- No package-manager or automatic external-module discovery exists.
- Custom ROBA roots are process environment defaults; every independently launched consumer must
  inherit the same values.
- Group membership uses Sway runtime container IDs, not persistent application identities.
- There is no group-delete command in this slice.
- Wofi and Sway configuration remain user-owned optional integrations.
- Tests use fake i3ipc and fake Wofi boundaries; perform a real desktop smoke test after install.
- DIX and this module execute trusted Python in-process and provide no security sandbox.

## Visual proof

A real screenshot or recording will be added only after a human run of the published instructions.
No synthetic visual is presented as execution evidence.

## Development verification

From the repository root, after preparing DIX and installing `sway/requirements.txt`:

```sh
DIX_REPOSITORY="$DIX_SOURCE_ROOT" "$DIX_SOURCE_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_SOURCE_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
python tests/verify_public_docs.py
```

## License

Apache License 2.0. See [`../LICENSE`](../LICENSE).
