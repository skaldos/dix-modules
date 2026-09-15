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
