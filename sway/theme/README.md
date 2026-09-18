# Sway theme value strands

This module contains small, stateless Sway theme value transformations. It deliberately has no
Sway IPC, application, CLI, state, or persistence dependency.

## Color

`skaldos/sway/theme/color.execute(value)` accepts exactly Sway-style `#RRGGBB` and `#RRGGBBAA`
hexadecimal colors. DIX Norn owns the structural string boundary; the Color composition owns the
color-format rule and its domain error.
