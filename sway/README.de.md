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
```

`ipc.command` bleibt die generische technische Sway-Grenze. Erst `nav/binding` besitzt die
fachliche Aufbereitung von `$dix_sway_nav`.

Zwei Commands werden bewusst getrennt ausgeliefert:

- `dix-sway-nav`: abhaengigkeitsarmer, zustandsloser Keybinding-Hotpath;
- `skaldos-sway-nav`: normale DIX-/Typer-CLI fuer Management und Tests.

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
$DIX_BIN/skaldos-sway-nav
$DIX_LAUNCHERS/dix-sway-nav.py
$DIX_LAUNCHERS/skaldos-sway-nav.py
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

## Management-CLI

```sh
skaldos-sway-nav basic set
skaldos-sway-nav basic left

skaldos-sway-nav windows-list set --ids 23 --ids 42
skaldos-sway-nav windows-list right --ids 23 --ids 42
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
