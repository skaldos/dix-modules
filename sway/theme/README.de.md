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

## Focused-Tab-Title-Colors

`skaldos/sway/theme/focused_tab_title_colors.execute(value)` akzeptiert exakt `border`,
`background` und `text`. Jeder Wert laeuft durch den Color-Strand und darf `#RRGGBB` oder
`#RRGGBBAA` verwenden.

## Background

`skaldos/sway/theme/background.execute(value)` akzeptiert exakt eine von zwei Varianten: ein Bild
mit absolutem `file`, `mode` (`stretch`, `fill`, `fit`, `center` oder `tile`) und verpflichtendem
`#RRGGBB`-`fallback_color`; oder Farbe mit exakt einem `#RRGGBB`-`color`. Das Ziel ist fest
`output *`. Der direkte Handler erzeugt entweder das Bildkommando oder
`output * bg #RRGGBB solid_color`. Er prueft weder Wallpaper-Existenz noch Bilddekodierung.

## Client-Theme-Knot

`skaldos/sway/theme/client_theme` exponiert sechs sichere Wirkungen fuer focused,
focused-inactive, focused-tab-title, unfocused, urgent und Background. Jede validiert ihren
vollstaendigen Input und nutzt die gemeinsame `skaldos/sway/core/ipc.command`-Grenze exakt einmal.

Die Function `execute(value)` ist ein toleranter `dix/norn/knot`: Vorhandene bekannte Felder
werden in deklarierter Reihenfolge durch ihren Feld-Strand verarbeitet und anschliessend an
ihren oeffentlichen Handler uebergeben. Fehlende bekannte Felder werden uebersprungen, unbekannte
Felder ignoriert. Ein leeres Mapping bewirkt daher nichts und liefert ein leeres Mapping. Knot
loest die lokalen Strand-Dependencies und die oeffentlichen Handler beim Graphaufbau aus seinem
unmittelbaren `client_theme`-Owner auf; der Wrapper uebergibt nur den Eingabewert. Die direkten
Handler bleiben einzeln komponierbar und validieren ihren vollstaendigen Input vor dem Sway-Command.

## Vollstaendige Theme-TOML-Application

`skaldos/sway/theme/theme.apply(file)` expandiert `~`, verlangt eine regulaere lesbare Datei und
parst das vollstaendige TOML-Dokument vor der ersten Sway-Wirkung. Einen relativen Bildpfad
materialisiert sie gegen das Verzeichnis der Theme-TOML, bevor sie das Root-Mapping genau einmal
an `client_theme.execute` uebergibt; absolute Bildpfade und Farbhintergruende bleiben
unveraendert. Bekannte Felder laufen in der Reihenfolge `focused`, `focused_inactive`,
`focused_tab_title`, `unfocused`, `urgent` und `background`. Andere Root-Felder werden ignoriert.
Ein Dokument ohne bekannte Felder ist ein erfolgreicher No-op.

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
