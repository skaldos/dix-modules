# Sway-Theme-Wertstrands

Dieses Modul enthaelt kleine Sway-Theme-Werttransformationen, eine explizit wirkende
Client-Theme-Grenze und eine schmale dateigetriebene Application. Es besitzt keine Abhaengigkeit
zu State, ROBA, Katalog oder Persistenz.

## Color

`skaldos/sway/theme/color.execute(value)` akzeptiert exakt Sway-Farben im Format `#RRGGBB` und
`#RRGGBBAA`. DIX Norn verantwortet die strukturelle String-Grenze; die Color-Composition
verantwortet die Farbformatregel und ihren Fachfehler.

## Client Colors

`skaldos/sway/theme/client_colors.execute(value)` akzeptiert ein flaches Mapping mit exakt
`border`, `background`, `text`, `indicator` und `child_border`. Die Modellgrenze verantwortet die
Mapping-Struktur. Jedes Feld wird unabhaengig durch den lokal komponierten Color-Strand
verarbeitet; das Ergebnis ist ein neues natives Dictionary.

## Client-Theme-Knot

`skaldos/sway/theme/client_theme` exponiert vier sichere Client-Color-Wirkungen fuer fokussierte,
fokussiert-inaktive, nicht fokussierte und dringende Clients. Jede akzeptiert ein vollstaendiges
Client-Colors-Mapping und nutzt die gemeinsame `skaldos/sway/core/ipc.command`-Grenze exakt einmal.

Die Function `execute(value)` ist ein toleranter `dix/norn/knot`: Vorhandene bekannte Felder
werden in deklarierter Reihenfolge durch `client_colors.execute` verarbeitet und anschliessend an
ihren oeffentlichen Handler uebergeben. Fehlende bekannte Felder werden uebersprungen, unbekannte
Felder ignoriert. Ein leeres Mapping bewirkt daher nichts und liefert ein leeres Mapping. Knot
loest die `client_colors`-Dependency und die oeffentlichen Handler beim Graphaufbau aus seinem
unmittelbaren `client_theme`-Owner auf; der Wrapper uebergibt nur den Eingabewert. Die direkten
Handler bleiben einzeln komponierbar und validieren ihren vollstaendigen Input vor dem Sway-Command.

## Vollstaendige Theme-TOML-Application

`skaldos/sway/theme/theme.apply(file)` expandiert `~`, verlangt eine regulaere lesbare Datei und
parst das vollstaendige TOML-Dokument vor der ersten Sway-Wirkung. Das unveraenderte Root-Mapping
wird genau einmal an `client_theme.execute` uebergeben. Aktuell bekannte Felder sind `focused`,
`focused_inactive`, `unfocused` und `urgent`; unbekannte Root-Felder wie `focused_tab_title` und
`background` ignoriert der aktuelle Knot bewusst. Ein Dokument ohne bekannte Felder ist ein
erfolgreicher No-op.

Die Application bietet weder Theme-Katalog noch Persistenz, Parser-Fallback, Vorabvalidierung
aller Wirkungen oder Rollback. Ein spaeter Farb- oder IPC-Fehler bleibt sichtbar; fruehere Commands
koennen dann bereits gewirkt haben.

## CLI und Installation

Die getrennte DIX-/Typer-Application exponiert exakt:

```sh
dix-sway-theme-cli theme apply --file /pfad/zum/theme.toml
```

Nur diesen Theme-Command samt generiertem Launcher installiert:

```sh
sway/theme/integrations/install
```

Der Installer liest `${DIX_ENV:-$HOME/.dix/env}`, erzeugt diese zentrale Environment-Datei nur
bei Abwesenheit und installiert niemals Themes oder Wallpaper. Die Umgebung muss
`DIX_SOURCE_ROOT`, `DIX_VENV`, `DIX_LAUNCHERS`, `DIX_BIN` und `SKALDOS_SWAY_ROOT` definieren.
