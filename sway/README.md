# skaldos/sway

External Sway integration for DIX. The implementation is added ticketwise; this directory is the
direct module root and is loaded explicitly as `skaldos/sway`.

## Ownership

`groups` owns private JSON membership. ROBA context `skaldos-sway` publishes only group names and
the active name. `active_members` and `navigation_target` are narrow atomic projections for the
navigation hot path. Their paths are set with:

- `SKALDOS_SWAY_GROUP_STATE_FILE`
- `SKALDOS_SWAY_ACTIVE_MEMBERS_FILE`
- `SKALDOS_SWAY_NAVIGATION_TARGET_FILE`

Build the broad Typer management CLI from `examples/launchers/skaldos_sway.toml` after cloning this
repository as `dix/modules/skaldos`. The caller must prepare the ROBA daemon and context through the
existing `dix/roba` management surface. The Wofi helpers are optional adapters and expect a
`SKALDOS_SWAY_MANAGEMENT` executable with the documented line-oriented commands; they never read
private state artifacts.

`examples/launchers/skaldos_sway_management.py` is the line/JSON management delivery consumed by
the Wofi adapters. Install or wrap it as `skaldos-sway-json`, or set
`SKALDOS_SWAY_MANAGEMENT`. Its `list-lines` and `memberships-lines` outputs are newline-delimited
names; mutations use explicit Group Application functions and emit compact JSON.

Group names are normalized non-empty single-line strings. The Wofi adapters frame group entries
separately from their `none` and `new` actions, so groups named `Keine Gruppe` or `+ Neue Gruppe`
remain ordinary selectable groups.

## Group navigation

Group navigation keeps Sway authoritative for direction: every move starts with the native
`focus left|right|up|down` command. If that command enters a container branch whose currently
focused leaf is not in the active group, the application reads a minimal group-free topology and
selects an allowed live leaf only inside that entered branch. Nested Sway `focus` order decides
between candidates; structural child order only completes an incomplete focus list.

This specifically supports hidden group members in stacked or tabbed branches without introducing
geometry, titles, application IDs, layout policy, ROBA, or a replacement navigation algorithm into
the hot path. A direct allowed native hit stays topology-free. If the entered branch has no
candidate, the existing native search and explicit origin restore remain in effect.
