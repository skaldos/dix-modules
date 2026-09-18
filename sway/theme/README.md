# Sway theme value strands

This module contains small Sway theme value transformations, one explicitly effectful client
theme boundary, and a narrow file-driven application. It has no state, ROBA, catalog, or
persistence dependency.

## Color

`skaldos/sway/theme/color.execute(value)` accepts exactly Sway-style `#RRGGBB` and `#RRGGBBAA`
hexadecimal colors. DIX Norn owns the structural string boundary; the Color composition owns the
color-format rule and its domain error.

## Client colors

`skaldos/sway/theme/client_colors.execute(value)` accepts one flat mapping with exactly
`border`, `background`, `text`, `indicator`, and `child_border`. The model boundary owns the
mapping structure. Every field is independently processed by the locally composed Color strand,
and the result is returned as a new native dictionary.

## Client theme Knot

`skaldos/sway/theme/client_theme` exposes four safe client-color effects for focused,
focused-inactive, unfocused, and urgent clients. Each accepts one complete client-color mapping and
uses the shared `skaldos/sway/core/ipc.command` boundary exactly once.

Its `execute(value)` function is a tolerant `dix/norn/knot`: known present fields are processed in
the declared order through `client_colors.execute` and then passed to their public handler. Missing
known fields are skipped and unknown fields are ignored. An empty mapping therefore has no effect
and returns an empty mapping. Knot resolves the `client_colors` dependency and public handlers
from its immediate `client_theme` owner while the graph is built; the wrapper passes only the
input value. The direct handlers remain independently composable and validate their complete input
before issuing a Sway command.

## Full Theme TOML application

`skaldos/sway/theme/theme.apply(file)` expands `~`, requires a regular readable file, and parses
the complete TOML document before the first Sway effect. It passes the unchanged root mapping
exactly once to `client_theme.execute`. The currently known fields are `focused`,
`focused_inactive`, `unfocused`, and `urgent`; unknown root fields such as `focused_tab_title` and
`background` are intentionally ignored by the current Knot. A document without known fields is a
successful no-op.

The application does not provide a Theme catalog, persistence, fallback parsing, prevalidation of
all effects, or rollback. A late color or IPC error remains visible and earlier commands may
already have taken effect.

## CLI and installation

The separate DIX/Typer application exposes exactly:

```sh
dix-sway-theme-cli theme apply --file /path/to/theme.toml
```

Install only this Theme command and its generated launcher with:

```sh
sway/theme/integrations/install
```

The installer reads `${DIX_ENV:-$HOME/.dix/env}`, creates that central environment file only when
it is absent, and never installs Themes or wallpapers. The environment must define
`DIX_SOURCE_ROOT`, `DIX_VENV`, `DIX_LAUNCHERS`, `DIX_BIN`, and `SKALDOS_SWAY_ROOT`.
