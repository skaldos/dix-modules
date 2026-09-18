# Sway theme value strands

This module contains small Sway theme value transformations and one explicitly effectful client
theme boundary. It deliberately has no application, CLI, state, ROBA, or persistence dependency.

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
and returns an empty mapping. The direct handlers remain independently composable and validate
their complete input before issuing a Sway command.
