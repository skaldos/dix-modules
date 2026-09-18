# Skaldos-Sway-Module

Dieser Branch liefert eine kleine externe DIX-Assembly fuer Sway-Navigation.

## Architektur

```text
skaldos/sway/core/ipc
├── focused_con_id
├── focus_direction
├── focus_con_id
├── live_con_ids
├── navigation_topology
└── command

skaldos/sway/nav/basic_nav
skaldos/sway/nav/windows_list_nav
skaldos/sway/nav/binding

skaldos/sway/nav/nav          # strikte programmatische Strategie-Fassade
skaldos/sway/nav/basic        # Typer-Target
skaldos/sway/nav/windows_list # Typer-Target
skaldos/sway/nav/cli          # Management-CLI

skaldos/sway/theme/color         # atomarer Sway-Hexfarben-Strand
skaldos/sway/theme/client_colors # flacher Fuenf-Farben-Modell-Strand
skaldos/sway/theme/focused_tab_title_colors # exakter Drei-Farben-Modell-Strand
skaldos/sway/theme/background    # strikter Bild-/Farbvarianten-Strand
skaldos/sway/theme/client_theme  # toleranter Knot plus sechs oeffentliche Sway-Wirkungen
skaldos/sway/theme/theme         # Application fuer vollstaendige TOML-Dateien
skaldos/sway/theme/cli           # DIX-/Typer-Theme-CLI
```

`ipc.command` bleibt die generische technische Sway-Grenze. Erst `nav/binding` besitzt die
fachliche Aufbereitung von `$dix_sway_nav`.

Zwei Commands werden bewusst getrennt ausgeliefert:

- `dix-sway-nav`: abhaengigkeitsarmer, zustandsloser Keybinding-Hotpath;
- `dix-sway-nav-cli`: normale DIX-/Typer-CLI fuer Management und Tests.

Beide lesen weder Group-Dateien noch ROBA oder Navigationsstate. Die aktive Low-Latency-Route liegt
als genau eine Runtime-Variable in Sway selbst.

## Source-Assembly

Die kanonische Entwicklungsassembly klont dieses Repository als `modules/skaldos` unter DIX:

```sh
git clone git@github.com:skaldos/dix.git ~/.dix/src/dix
cd ~/.dix/src/dix/modules
git clone --branch sway git@github.com:skaldos/dix-modules.git skaldos
```

DIX-Umgebung und die eine externe Runtime-Abhaengigkeit vorbereiten:

```sh
cd ~/.dix/src/dix
uv sync --extra cli
uv pip install --python .venv/bin/python -r modules/skaldos/sway/requirements.txt
```

## Environment und Installation

Fehlt `~/.dix/env`, erzeugt der Installer sie aus der mitgelieferten Vorlage:

```sh
~/.dix/src/dix/modules/skaldos/sway/nav/integrations/install
~/.dix/src/dix/modules/skaldos/sway/theme/integrations/install
```

Fuer eigene Ablagen wird `~/.dix/env` vor der Installation angelegt oder bearbeitet:

```sh
export DIX_SOURCE_ROOT="$HOME/.dix/src/dix"
export SKALDOS_SWAY_ROOT="$DIX_SOURCE_ROOT/modules/skaldos/sway"
export DIX_VENV="$DIX_SOURCE_ROOT/.venv"
export DIX_LAUNCHERS="${XDG_DATA_HOME:-$HOME/.local/share}/dix/launchers"
export DIX_BIN="$HOME/.local/bin"
```

Eine andere Environment-Datei kann fuer Installer und Commands explizit gewaehlt werden:

```sh
DIX_ENV="$HOME/pfad/zu/dix.env" \
  "$SKALDOS_SWAY_ROOT/nav/integrations/install"
```

Die wiederholbare Installation erzeugt:

```text
$DIX_BIN/dix-sway-nav
$DIX_BIN/dix-sway-nav-cli
$DIX_LAUNCHERS/dix-sway-nav.py
$DIX_LAUNCHERS/dix-sway-nav-cli.py
$DIX_BIN/dix-sway-theme-cli
$DIX_LAUNCHERS/dix-sway-theme-cli.py
```

## Sway-Konfiguration

`sway/nav/integrations/sway/config` kopieren oder inkludieren und `/home/YOU` durch das reale Home
ersetzen. Entscheidend ist:

```sway
set $dix_sway_nav basic
bindsym $mod+h exec --no-startup-id $dix_bin/dix-sway-nav left $$dix_sway_nav
bindsym $mod+j exec --no-startup-id $dix_bin/dix-sway-nav down $$dix_sway_nav
bindsym $mod+k exec --no-startup-id $dix_bin/dix-sway-nav up $$dix_sway_nav
bindsym $mod+l exec --no-startup-id $dix_bin/dix-sway-nav right $$dix_sway_nav
```

Das doppelte Dollarzeichen ist zwingend: Sway expandiert die Route beim Tastendruck statt bereits
beim Laden der Konfiguration.

## Optionale Theme-Strands und Client-Wirkung

`sway/theme` ist eine dritte, unabhaengig ladbare Modulwurzel. Sie komponiert `dix/norn/strand` und
`dix/norn/knot`. Fuer Client-Wirkungen haengt sie an der schmalen Sway-Core-IPC-Grenze, aber nicht
an Navigation, State, ROBA, Applications oder einer CLI.

```text
skaldos/sway/theme/color.execute(value)
  String-Grenze -> Fachvalidierung als #RRGGBB oder #RRGGBBAA -> String-Grenze

skaldos/sway/theme/client_colors.execute(value)
  flache Modellgrenze -> fuenf lokal aliasierte Color-Aufrufe -> flache Modellgrenze

skaldos/sway/theme/focused_tab_title_colors.execute(value)
  exaktes border/background/text-Modell -> drei Color-Aufrufe -> exaktes Modell

skaldos/sway/theme/background.execute(value)
  exakte Bild- oder Farbvariante -> kanonisches Background-Mapping

skaldos/sway/theme/client_theme.execute(value)
  vorhandene bekannte Felder -> Feld-Strand -> oeffentlicher set_*-Handler -> Feldresultat
```

Client Colors verlangt exakt `border`, `background`, `text`, `indicator` und `child_border`.
`focused_tab_title` verlangt stattdessen exakt `border`, `background` und `text`. Background ist
entweder ein Bild mit absolutem Pfad, einem der Modi `stretch`, `fill`, `fit`, `center` oder `tile`
und einer `#RRGGBB`-Fallbackfarbe oder exakt eine `#RRGGBB`-Farbe. Der tolerante Knot bindet diese
Strands und alle sechs Handler beim Graphaufbau aus seinem unmittelbaren Owner. Er ueberspringt
fehlende bekannte und ignoriert unbekannte Felder.

Die Theme-Application liest ein vollstaendiges TOML-Dokument vor der ersten Wirkung. Einen
relativen Bildpfad materialisiert sie vor der Delegation gegen das Verzeichnis der Theme-TOML;
eine Wallpaper-Existenz wird nicht behauptet. Der Knot wendet `focused`, `focused_inactive`,
`focused_tab_title`, `unfocused`, `urgent` und `background` in dieser Reihenfolge an. Background
zielt immer auf `output *` und erzeugt entweder ein Bildkommando oder
`output * bg #RRGGBB solid_color`. Andere Root-Felder bleiben ignoriert. Eine Datei wird ueber die
getrennte Management-CLI angewendet:

```sh
dix-sway-theme-cli theme apply --file /pfad/zum/theme.toml
```

Der dedizierte Theme-Installer installiert nur diesen Command und seinen generierten Launcher. Er
kopiert weder Themes noch Wallpaper und verwendet dieselbe zentrale `DIX_ENV`-Datei.

## Management-CLI

```sh
dix-sway-nav-cli basic set
dix-sway-nav-cli basic left

dix-sway-nav-cli windows-list set --ids 23 --ids 42
dix-sway-nav-cli windows-list right --ids 23 --ids 42
```

`set` aendert die einzelne Sway-Runtime-Route. Richtungscommands fuehren die gewaehlte Strategie
direkt aus und eignen sich fuer manuelle Tests.

## Direkter Hotpath

```sh
dix-sway-nav left basic
dix-sway-nav right windows-list 23 42
```

Ungueltige Strategie oder Window-IDs fallen best effort auf genau einen nativen Schritt derselben
Richtung zurueck. Die normalen DIX-Applications und die Management-CLI bleiben strikt und
uebernehmen diese Desktop-Fallbackpolicy nicht.

## Entwicklungspruefungen

```sh
cd ~/.dix/src/dix/modules/skaldos
DIX_REPOSITORY=~/.dix/src/dix ~/.dix/src/dix/.venv/bin/python -m pytest -q
~/.dix/src/dix/.venv/bin/python -W error -m compileall -f -q sway tests
```
