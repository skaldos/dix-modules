# Sway-Theme-Wertstrands

Dieses Modul enthaelt kleine zustandslose Transformationen fuer Sway-Theme-Werte. Es besitzt
bewusst keine Abhaengigkeit zu Sway IPC, Application, CLI, State oder Persistenz.

## Color

`skaldos/sway/theme/color.execute(value)` akzeptiert exakt Sway-Farben im Format `#RRGGBB` und
`#RRGGBBAA`. DIX Norn verantwortet die strukturelle String-Grenze; die Color-Composition
verantwortet die Farbformatregel und ihren Fachfehler.
