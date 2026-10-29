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
window and attaches. Its four owned roles are logo/non-secret status (top left), the broad
ROBA Loom (top right), the staged Store workbench (bottom left) and Owner Shell (bottom right). Every pane has a visible title. A repeated start
focuses the running workbench. If that process exited, its pane and error remain visible; the next
explicit UI start respawns that same role instead of creating a duplicate. Detach leaves all
processes alive. Continue to use `dix-cockpit attach|status|stop|reset` for lifecycle operations;
the UI intentionally duplicates none of them.

The master helper validates the live owner artifact inside its own process and creates the Loom
connection there. Its Control token is never passed in argv, a seed file, tmux environment,
options, role metadata or titles. The token is intentionally visible and editable inside this
personal owner workbench. In the top-right Loom, Enter only inspects the selected ObjectReference and opens a local
draft. Space is the sole provider execution path and keeps the existing confirmation. Provider
errors preserve the workbench session.

tmux keeps the isolated key surface described above: `C-a` (or `C-b`) is the prefix, `h/j/k/l`
navigates panes, `C-h`/`C-l` changes windows, `H/J/K/L` resizes, and `Escape` enters vi copy mode.
The configured copy/paste adapters prefer the system clipboard and fall back to the private tmux
buffer. No automatic target provisioning, file import/export, save, sync or runner is
part of the master Loom; the separate read-only Store catalog is described below.

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

## Staged Store workbench (UP-066 / UP-067)

Re-run `./cockpit/integrations/install-ui` after updating the sources. It also installs the
internal `dix-cockpit-store-workbench --session dix --logo dix` helper. The normal entry stays
`dix-cockpit-ui start --session dix --logo dix`. Start is idempotent: it completes missing owned
roles, focuses the existing Loom and deliberately respawns exited Loom/Store panes; it never
adopts foreign or ambiguous pane roles. Detach keeps all four processes alive.

The **bottom-left Store pane** is now the primary local registration/editor interface:

| Key | Effect in this Store pane only |
| --- | --- |
| :o | Open/focus a saved catalog-root Store in its own workspace |
| :n | New provider draft; one provider opens directly, multiple providers require a choice |
| Enter on a catalog row | Open its local definition, not its target |
| Enter on a container | Drill within the same draft |
| Enter on an atomic value cell | Native inline cell editor at the cell, not a footer TOML prompt |
| Enter / Esc in the editor | Accept locally / cancel only this cell |
| :w / Ctrl+S | Validate and commit the complete Store once to the local catalog |
| q | Parent; at the catalog root remain alive |
| :r / Ctrl+R | Guard the draft, then reload the catalog |
| :q | Guard the draft, then explicitly exit this Store workbench |
| :wq | Save; leave the pane only after success |
| :q! | Deliberately discard the draft and leave without a prompt |
| h j k l / arrows | Native row/column navigation |
| PageUp / PageDown | Page through longer sheets |
| gg / G | First / last row |

`:` opens only the Cockpit prompt for `n`, `w`, `q`, `wq`, `q!`, `r`, `o`.
Tokens are trimmed; empty or unknown tokens show a local message and otherwise do nothing.
No parameters, shell commands, regex or Ex language. The Store fully imports VisiData **3.4**,
checks its SettingsMgr/command/input boundary before curses, clears its entire process-local
binding registry and registers only these 17 keys. Its compact sheet-local right status
reserves input space for prompts in the split master pane. An incompatible version or registry aborts
startup with exit code 2 and a fixed credential-free message. Menus, `i`, `-`, generic file
save and general spreadsheet shortcuts are unreachable.
**`a`, `z Ctrl+S` and `gq` have no compatibility aliases.**

Strings need no quotes; typing replaces the initial cell value (native VisiData behavior).
Existing integers/floats remain their original types; floats must be finite. Booleans accept
`true` or `false` (case-insensitive), not `yes`/`no` or `0`/`1`. Invalid input preserves the old
value and shows a local error. The sole shipped ROBA draft has no Boolean field; that type boundary
is verified with a test-only terminal fixture, not an extra installed provider.

Accepted cells only change the draft and its visible **DIRTY**/modified marker. No catalog call
occurs until `:w` or **Ctrl+S**. New drafts use one `create`; existing definitions
use one `update`. Duplicate IDs, unknown providers, invalid definitions or local transport failures
preserve the old baseline and catalog. Correct the same dirty draft and retry.

Leaving a dirty draft (root back, New/switch, Reload or explicit exit) asks **Save / Discard /
Cancel**: `s` commits once and continues only on success; `d` discards without writing; `c` or Esc
stays in the same draft. Navigation inside containers never asks. Credentials may intentionally be
visible in the personal editor, but no target is contacted and no credential goes into process
arguments, tmux metadata/titles, breadcrumbs or ordinary status/error lines. The catalog remains
volatile: stop/start or reset discards it. “Persistent pane” does not mean file persistence.

The historical detached-draft flow remains only in the explicit dual-pane underlay, not as a
leading master flow. The broad master Loom no longer binds zS/zN Store entry points.
VisiData handles native `Ctrl+Q` in its main loop, outside the binding registry.

The Store process therefore checks its draft after `vd.run()` returns: a dirty draft gets the
same Save/Discard/Cancel choice as a plain terminal prompt after curses ends. Cancel or failed
Save returns to the same draft/path/cursor; Save or Discard exits explicitly. This does not patch
VisiData or affect the other workbenches. Forced OS/process/terminal destruction is not a guarded
navigation command. The read-only dual browser and the top-right broad ROBA Loom
retain their navigation/Loom keys, except the deliberately removed master Store hooks.
Only the master Loom starts directly without an Enter prelude;
logo/status remain visible in their own pane. Other workbenches keep their branding and start
contract. VisiData's global quit behavior is not patched.

## One owned workspace per saved Store (UP-068)

Re-run `./cockpit/integrations/install-ui` after updating. It also delivers
`dix-cockpit-store-status`. Both views load their definition privately by session, Store ID and
logo; no connection or capability is passed in their launch arguments.

Select a saved entry in the bottom-left catalog, then `:o`, Enter:

```text
Store window
+--------------------------------+
| logo + privileged status       |
| full definition + revision     |
+--------------------------------+
| exactly one read-only browser  |
| rooted at the selected Store   |
+--------------------------------+
```

- Enter in the master remains local definition/cell interaction, not a window-open operation.
- `:o` is only for a saved catalog-root entry. Drafts, children, empty selection and removed entries
  have neither save nor window effects; failures remain visible.
- Repeating focuses the same uniquely owned window. Name/index are presentation; renaming/moving
  within the session is supported. Use normal tmux navigation for routine window switching.
- A dead or missing owned pane is repaired without replacing its healthy counterpart. A manually
  closed window is recreated on the next `:o`.
- Every successful whole Store save rotates a private random revision, including identical saves.
  Public `list`/`get` and drafts remain exactly `store_id`, `provider`, `connection`. Revisions are
  not definition/token hashes. On the next `:o`, drift rebuilds both views; an old browser is not
  left running as apparently current access.
- An open browser refuses further reads after its saved definition changes until reopened.
  There is no watcher, sync or automatic reconnect.
- Foreign, duplicate, cross-session or inconsistent ownership metadata fails closed without
  adoption or deletion of foreign resources. Fresh-creation failure removes only its new window.
  A failed rebuild can leave a visible repair/recreate requirement; old access is stopped first.

The browser stays in its selected Store. Enter drills containers or inspects atomic values;
`q`/`zB` goes to the parent and stays alive at the Store root; `zU` returns to that same root,
Ctrl+R reloads. Close a scalar inspect sheet with native VisiData-q. The selected browser has no
catalog New/Edit/Rename/Remove commands and calls only the positive provider surface
`root`/`children`/`inspect`. Provider errors stay visible without deleting the window or catalog
entry. This is not a sandbox for arbitrary Python code deliberately executed by its owner.

Context connections may expose keys and readable instances; a connection with `instance_id`
starts directly at that instance's keys. Existing instance connections can be materialized through
the catalog API, then reviewed/saved in the master pane. New's small draft remains the existing
Context form; UP-068 does not invent another provider or draft variant.

**Status is deliberately privileged:** locator, token and scope are visible and copyable there.
Never forward them through argv, titles, tmux options/environment, ordinary error logs or unchecked
shared captures. Even private session recordings can contain that display. Stop/reset still owns
runtime cleanup and discards the volatile catalog; there is no autosave/export. Use a fresh runtime
after the record-format update; old running catalog contents are not silently migrated.

## Historical explicit dual-pane Stores (UP-065)

Re-run `./cockpit/integrations/install-ui` after updating. It also installs the internal
`dix-cockpit-store-browser` helper; the base runtime remains VisiData-free. Start the master as
above. This historical explicit underlay is retained for regression, not as the leading UX.
The master Loom has no zS/zN Store entry points. From the owner shell or an activated external terminal:

```sh
dix-cockpit-ui stores --session dix --logo dix
```

This requires an already healthy owned Cockpit. Outside tmux it attaches; inside it focuses the
window. The window has exactly two independently navigable browsers, **Stores A** and **Stores B**.
The isolated tmux prefix and pane/window navigation above still apply. Reopening focuses running
panes; exited panes remain visible and are respawned only on explicit reopen. Detach preserves
the workspace; `dix-cockpit stop|reset` remains the only lifecycle cleanup.

### Register an existing access, not a new target

1. Create any target Context, Instance, token, socket or grant separately in your administrative
   terminal. New Store never creates or repairs these resources.
2. Press `zN` in one of the explicit historical browsers. Choose `roba` (the only provider); Enter accepts
   the prefilled provider. This opens a detached local draft with `store_id`, `provider` and
   `connection`. No target is contacted.
3. Use Enter to drill into `connection`, and `e` to edit scalars as **TOML literals**, for example
   `"project"`, `"unix:/absolute/existing/ctx.sock"`, `"paste-the-existing-token-here"`, `5.0`.
   Set a non-empty `store_id` at the root. The default is the existing canonical direct Context
   variant: `context_id`, `context_locator`, `token`, `timeout`. Add `instance_id` with `a` to scope
   it to one existing Instance. For an existing capability socket remove the `token` field with
   `d`; use that socket's direct locator. The provider also accepts the existing complete
   DIX-ROBA Control capability variants, not an alternative credential schema.
4. Press `zC` (`commit-local-definition`) at any draft depth and confirm once. Only the complete
   local definition is written to the private Cockpit catalog. `q` returns; reload the browser
   root with `Ctrl-R`. Closing without `zC` discards changes.
5. Enter on the Store explicitly reads its target. Missing/offline/unauthorized targets fail here,
   not during registration. Use `zB` to return, correct the local access with `zE`, then reload.

| Browser key | Effect |
| --- | --- |
| Enter | Read selected container or inspect a value; no provider mutation |
| zB | Parent; from a Store root return to the virtual root |
| zU | Virtual root |
| Ctrl-R | Reload only this pane; also refresh the shared catalog |
| zN | New local Store via provider selection and detached draft |
| zE | Edit the selected Store's local definition; zC commits explicitly |
| zR | Rename only the local registration |
| zX | Confirm removal of only the local registration |
| q | VisiData back/quit; no daemon cleanup |

Both browsers read the same live catalog, but selection, cursor, path and errors are pane-local.
The fixed header shows a breadcrumb or a visible error. Empty/error states remain navigable back
to `/`. ROBA exposes only Context metadata, readable Instances, keys and values; Control-only
access does **not** imply a Context owner credential. Use a separately registered Context access
for its data. A token with only Instance read grants sees only those readable resources.
Create, delete, write, token, socket, grant and management offers are not available, even through
manipulated node IDs. The master itself deliberately retains its original broad owner Loom.

The catalog is volatile private ROBA state, serialized per Cockpit session. Other processes in
the same session see explicit commits on reload; other sessions do not. Local edit/rename/remove
never contact the external target and never delete or revoke its resources. A full stop/start or
reset discards the catalog. There is no file persistence, autosave, snapshot, import/export,
transfer, second provider, sync or runner.

Credentials may be displayed/edited/copied in the personal Owner draft, but are never placed in
argv, tmux metadata/environment/titles, breadcrumbs or ordinary status/error logs. The separate
privileged Store-status pane above deliberately displays the complete definition. Browser helpers
receive only session/logo/side and obtain the private capability inside their process. Terminal
recordings can still capture an intentionally displayed token: use short-lived test credentials,
keep recordings private and inspect/redact before sharing.
