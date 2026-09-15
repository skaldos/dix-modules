# `skaldos/sway`

Topology-aware Sway window-group navigation assembled with DIX and coordinated through ROBA.

[Deutsch](README.de.md) · [Repository overview](../README.md) ·
[DIX](https://github.com/skaldos/dix) · [ROBA](https://github.com/skaldos/roba)

> **Public Alpha:** this module is already useful in a real Sway workflow, but setup and source
> contracts may still change. It is delivered as source, not as a Python package.

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
export DIX_ROOT=$SKALDOS_WORKSPACE/dix
```

Do not place the external checkout below `dix/modules` before the initial DIX sync. Directories
present there are inputs to a locally built DIX distribution. Preparing the committed DIX source
first keeps that distribution limited to DIX-owned modules; the external checkout remains a source
consumer added afterwards.

## 2. Prepare the DIX environment

DIX already points to the sibling `../roba` source in this layout. Sync its declared extras, then
install the Sway-owned requirements into the same environment:

```sh
cd "$DIX_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba

git clone https://github.com/skaldos/dix-modules.git "$DIX_ROOT/modules/skaldos"
export SWAY_ROOT=$DIX_ROOT/modules/skaldos/sway

uv pip install --python "$DIX_ROOT/.venv/bin/python" -r "$SWAY_ROOT/requirements.txt"
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

## 3. Define local Sway state files

Use one private directory and export all three boundaries consistently:

```sh
export SKALDOS_SWAY_STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/skaldos/sway
export SKALDOS_SWAY_GROUP_STATE_FILE=$SKALDOS_SWAY_STATE_DIR/groups.json
export SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$SKALDOS_SWAY_STATE_DIR/active-members
export SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$SKALDOS_SWAY_STATE_DIR/navigation-target
mkdir -p "$SKALDOS_SWAY_STATE_DIR"
```

- `groups.json` is private group ownership and contains names plus stored `con_id` lists.
- `active-members` is a narrow, newline-terminated list used by the navigation hot path.
- `navigation-target` contains exactly `basic` or `group` plus a newline.

Treat `groups.json` as local user state. The projection files are replaceable outputs and must not
be edited into malformed values.

## 4. Build the DIX ROBA launcher

The management entry needs a running ROBA daemon, the DIX control registry, and a managed context.
Build the committed DIX launcher once:

```sh
mkdir -p "$DIX_ROOT/.local/launchers"
"$DIX_ROOT/.venv/bin/python" -m dix.bootstrap build \
  "$DIX_ROOT/examples/launchers/dix_roba.toml" \
  --output "$DIX_ROOT/.local/launchers/dix-roba.py" \
  --replace

export DIX_ROBA=$DIX_ROOT/.local/launchers/dix-roba.py
```

The generated launcher uses explicit module sources. It is not a daemon and performs no discovery.

## 5. Start ROBA and create `skaldos-sway`

Use the proven defaults: daemon ID `default`, runtime root `~/.roba/runtime`, and logs root
`~/.roba/logs`.

```sh
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" managed start
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" control create_context \
  --context_id skaldos-sway
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" daemon status
```

`managed start` starts ROBA and bootstraps the DIX control context. `create_context` then creates
the module context and its manager socket. These commands print capability-bearing result data;
do not paste tokens into documentation, logs, or tickets.

Do not run `create_context` repeatedly against an already existing context. A duplicate is a
visible error, not an attach operation.

## 6. Install the two transparent wrappers

The wrappers only locate the source tree and execute the committed entrypoint with DIX's Python:

```sh
mkdir -p "$HOME/.local/bin"
ln -sfn "$SWAY_ROOT/integrations/bin/skaldos-sway-nav" \
  "$HOME/.local/bin/skaldos-sway-nav"
ln -sfn "$SWAY_ROOT/integrations/bin/skaldos-sway-json" \
  "$HOME/.local/bin/skaldos-sway-json"
export PATH=$HOME/.local/bin:$PATH
```

They derive the documented layout through the real symlink target. For a different source shape,
set absolute `SKALDOS_DIX_ROOT` and `SKALDOS_SWAY_ROOT` values. Do not use an unexpanded literal
`~` in either variable.

The wrappers never start ROBA. `skaldos-sway-json` is the broad DIX/ROBA management path;
`skaldos-sway-nav` is the direct dependency-light navigation path.

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

## 8. Test navigation directly

An explicit target bypasses the route file without changing it:

```sh
skaldos-sway-nav --target basic right
skaldos-sway-nav --target group left
```

Without `--target`, the entry reads `navigation-target`; a missing route file defaults to `basic`:

```sh
skaldos-sway-nav right
```

Navigation emits one compact JSON result. A group target requires a valid active-member projection.
The direct process intentionally imports no Typer, Click, ROBA, HTTPX, or Pydantic.

## 9. Optional Wofi commands

With `skaldos-sway-json` on `PATH` and the same state variables exported:

```sh
"$SWAY_ROOT/integrations/wofi/select"
"$SWAY_ROOT/integrations/wofi/add"
"$SWAY_ROOT/integrations/wofi/remove"
```

The existing-entry menus invoke Wofi with `--no-custom-entry`. Pressing Enter on the initially
highlighted row therefore commits that row without requiring a cursor movement. Only the separate
"new group" dialog accepts free text.

Override `SKALDOS_SWAY_MANAGEMENT`, `SKALDOS_SWAY_WOFI`, or `SKALDOS_SWAY_WOFI_NAME` only when you
intentionally own the replacement command. These variables are shell command boundaries, not a
DIX API.

## 10. Add the Sway bindings

The complete maintained fragment is
[`integrations/sway/config`](integrations/sway/config). Copy it into the Sway configuration and
replace `/home/YOU` plus `path/to/workspace` with absolute values:

```text
set $skaldos_home /home/YOU
set $skaldos_sway $skaldos_home/path/to/workspace/dix/modules/skaldos/sway
set $skaldos_state $skaldos_home/.local/state/skaldos/sway

set $skaldos_nav env SKALDOS_SWAY_GROUP_STATE_FILE=$skaldos_state/groups.json SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$skaldos_state/active-members SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$skaldos_state/navigation-target $skaldos_home/.local/bin/skaldos-sway-nav
set $skaldos_manage env SKALDOS_SWAY_GROUP_STATE_FILE=$skaldos_state/groups.json SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$skaldos_state/active-members SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$skaldos_state/navigation-target SKALDOS_SWAY_MANAGEMENT=$skaldos_home/.local/bin/skaldos-sway-json

exec_always --no-startup-id mkdir -p $skaldos_state

bindsym $mod+h exec --no-startup-id $skaldos_nav left
bindsym $mod+j exec --no-startup-id $skaldos_nav down
bindsym $mod+k exec --no-startup-id $skaldos_nav up
bindsym $mod+l exec --no-startup-id $skaldos_nav right

bindsym $mod+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/select
bindsym $mod+Shift+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/add
bindsym $mod+Ctrl+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/remove
```

Choose bindings that do not conflict with your configuration. Reload and perform a basic smoke
test:

```sh
swaymsg reload
skaldos-sway-json list-lines
skaldos-sway-nav --target basic right
```

The final command moves focus. Once a group has live members, select it and test the fixed bindings.

## Shutdown and restart

Stop the default daemon explicitly:

```sh
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" daemon stop
```

All ROBA contexts and coordination state disappear. The private JSON and projection files remain
because they are separate local files, not ROBA state.

After a ROBA-only restart:

```sh
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" managed start
"$DIX_ROOT/.venv/bin/python" "$DIX_ROBA" control create_context \
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
Rebuild `dix-roba.py` from the committed DIX spec shown above. Do not hand-remove its module list.

### Manager socket is missing

A typical failure names a missing socket below
`~/.roba/runtime/daemons/default/contexts/dix.control/sockets/`. Confirm that `managed start`
succeeded, then create `skaldos-sway` exactly once. If the daemon was restarted, its old sockets
and contexts no longer exist and both steps must be repeated.

### A socket path contains the wrong `~` or becomes relative

Shells do not expand `~` inside arbitrary quoted variables or generated strings. The public
quickstart uses ROBA's proven defaults. If you deliberately pass custom roots or wrapper overrides,
use absolute paths and pass the same values to daemon, control, context management, and every
consumer. Partial custom-root configuration is unsupported in this alpha guide.

### ROBA is running, but `skaldos-sway` is missing

Daemon status alone is insufficient. Run the `control create_context --context_id skaldos-sway`
command. If it reports that the context already exists, do not create a second one; inspect the
manager-socket path and ensure every command uses the same daemon configuration.

### Navigation reports a missing or invalid projection

Check the three `SKALDOS_SWAY_*_FILE` values in the calling process. `navigation-target` must be
exactly `basic\n` or `group\n`; `active-members` must be one newline-terminated, space-separated
line of positive IDs. Re-run `skaldos-sway-json select <group>` to regenerate both. Do not repair
malformed files by guessing at another format.

### Sway or i3ipc cannot connect

Verify all of the following from the same environment:

```sh
printf '%s\n' "$SWAYSOCK"
swaymsg -t get_tree >/dev/null
"$DIX_ROOT/.venv/bin/python" -c 'import i3ipc; print(i3ipc.__version__)'
```

If the import fails, repeat the explicit requirements installation. If `swaymsg` fails, run the
command inside the correct Sway session; the module does not create or discover a display server.

## Known alpha limits

- No daemon or context is started automatically.
- No package-manager or automatic external-module discovery exists.
- The documented operational path uses the default ROBA roots; custom roots need end-to-end owner
  verification.
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
DIX_REPOSITORY="$DIX_ROOT" "$DIX_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
python tests/verify_public_docs.py
```

## License

Apache License 2.0. See [`../LICENSE`](../LICENSE).
