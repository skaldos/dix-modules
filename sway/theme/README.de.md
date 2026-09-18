# Sway-Theme-Wertstrands

Dieses Modul enthaelt kleine zustandslose Transformationen fuer Sway-Theme-Werte. Es besitzt
bewusst keine Abhaengigkeit zu Sway IPC, Application, CLI, State oder Persistenz.

## Color

`skaldos/sway/theme/color.execute(value)` akzeptiert exakt Sway-Farben im Format `#RRGGBB` und
`#RRGGBBAA`. DIX Norn verantwortet die strukturelle String-Grenze; die Color-Composition
verantwortet die Farbformatregel und ihren Fachfehler.

## Client Colors

`skaldos/sway/theme/client_colors.execute(value)` akzeptiert ein flaches Mapping mit exakt
`border`, `background`, `text`, `indicator` und `child_border`. Die Modellgrenze verantwortet die
Mapping-Struktur. Jedes Feld wird unabhaengig durch den lokal komponierten Color-Strand
verarbeitet; das Ergebnis ist ein neues natives Dictionary.
