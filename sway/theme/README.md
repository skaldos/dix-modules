# Sway theme value strands

This module contains small, stateless Sway theme value transformations. It deliberately has no
Sway IPC, application, CLI, state, or persistence dependency.

## Color

`skaldos/sway/theme/color.execute(value)` accepts exactly Sway-style `#RRGGBB` and `#RRGGBBAA`
hexadecimal colors. DIX Norn owns the structural string boundary; the Color composition owns the
color-format rule and its domain error.

## Client colors

`skaldos/sway/theme/client_colors.execute(value)` accepts one flat mapping with exactly
`border`, `background`, `text`, `indicator`, and `child_border`. The model boundary owns the
mapping structure. Every field is independently processed by the locally composed Color strand,
and the result is returned as a new native dictionary.

`skaldos/sway/theme/client_theme` exposes four safe client-color effects for focused,
focused-inactive, unfocused, and urgent clients. Each accepts one complete client-color mapping and
uses the shared Sway Core IPC command boundary.
