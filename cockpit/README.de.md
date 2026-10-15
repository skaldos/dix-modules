# DIX Cockpit

DIX Cockpit ist eine benannte, isolierte und privilegierte Terminal-Runtime. Jede Session verbindet:

- einen eigenen ROBA-Daemon samt nativer Control-Capability;
- eine Session auf einem ausschliesslich Cockpit gehoerenden tmux-Server;
- eine isolierte Owner-Zsh mit privaten Startup-Dateien und eigener History;
- ein getrenntes DIX- oder ROBA-Logo-/Status-Pane.

Der Haupt-Lifecycle verwendet weder DIX Control noch Daemon-Katalog, VisiData, Host-tmux oder
Host-Zsh-Dateien. Der vorhandene Katalog-/Provider-Code ist Legacy und am `dix-cockpit`-Einstieg
nicht beteiligt.

## Voraussetzungen und Installation

DIX muss `dix/state`, `dix/cli`, `dix/norn` und `dix/roba` liefern. Sein Environment muss
`DIX_SOURCE_ROOT`, `DIX_VENV`, `DIX_LAUNCHERS` und `DIX_BIN` setzen. ROBA muss in dieser
Python-Umgebung bereits vorhanden sein. Auf dem Host werden tmux und Zsh benoetigt; Chafa sowie
Wayland-/X11-Clipboardtools sind optional.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; das ist der Default
./cockpit/integrations/install
```

Der Installer ist wiederholbar. Er baut nur Haupt-, Owner-Shell- und Status-Launcher und
installiert namespaced Wrapper, private tmux-/Zsh-Configs sowie beide geprueften Logos. Das
DIX-Environment wird nicht bearbeitet; Host-tmux-/Zsh-Configs werden weder gelesen noch
ueberschrieben. Er assembliert ein explizites privates Runtime-Modul, das nur die drei Runtime-
Applications und ihre vier Cockpit-Compositions enthaelt. Die Launcher laden oder benoetigen das
getrennt erhaltene VisiData-Modul daher nicht.

Optionale prozesslokale Overrides:

```sh
export DIX_COCKPIT_RUNTIME_ROOT="${XDG_RUNTIME_DIR:-/tmp}/dix-cockpit"
export DIX_COCKPIT_STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/skaldos/cockpit"
export DIX_COCKPIT_TMUX_CONFIG="$DIX_LAUNCHERS/cockpit/tmux.conf"
export DIX_COCKPIT_ZSH_CONFIG="$DIX_LAUNCHERS/cockpit/zsh/.zshrc"
export DIX_COCKPIT_ASSET_ROOT="$DIX_LAUNCHERS/cockpit/assets"
```

`DIX_COCKPIT_RUNTIME_ROOT` muss kurz bleiben. Cockpit prueft das harte Plattformlimit fuer
Unix-Socketpfade vor jeder Erzeugung.

## Commands

```sh
dix-cockpit start  [--session NAME] [--logo dix|roba]
dix-cockpit attach [--session NAME]
dix-cockpit status [--session NAME]
dix-cockpit stop   [--session NAME]
dix-cockpit reset  [--session NAME] [--logo dix|roba]
```

Session und Logo verwenden standardmaessig `dix`.

- `start` erzeugt oder verwendet die vollstaendige Runtime und attached.
- `attach` und `status` erzeugen oder reparieren nichts. Status liefert JSON und einen Exitcode
  ungleich null, solange die Gesamtruntime nicht gesund ist.
- `stop` beendet zuerst nur den nachweislich besessenen ROBA-Daemon, entfernt fluechtige
  Capabilitydaten und stoppt danach die eigene tmux-Session. Der tmux-Server endet erst nach seiner
  letzten Session. Logs und Shell-History bleiben erhalten.
- `reset` fuehrt einen ownership-geprueften Stop aus, startet mit neuer Capability und attached.
- Detach oder Clientverlust stoppt nichts. `stop` und `reset` innerhalb der Zielsession werden
  abgewiesen; zuerst detachen.

Ein laufender eigener Daemon mit fehlender tmux-Session wird durch `start` wieder aufgebaut. Eine
lebende tmux-Session mit fehlendem oder ungueltigem Daemon wird nicht still repariert; dafuer ist
`reset` da. Fremde Daemons, kaputte Owner-Artefakte und fremde tmux-Sessions werden nie adoptiert
oder gestoppt.

Ein fehlgeschlagener ROBA-Statusrequest gilt nur dann als sicher abwesend, wenn beide erwarteten
Runtime-Endpunkte fehlen. Existiert noch mindestens ein Endpunkt, meldet der Status eine unklare
Runtime und jede Lifecycle-Mutation scheitert fail-closed. Der dedizierte tmux-Server und jede
Cockpit-Session tragen getrennte nicht geheime Ownership-Marker; ein erreichbarer unmarkierter
Server wird auch ohne vorhandene Zielsession niemals adoptiert.

## Owner-Shell und tmux

Das erste Window enthaelt die Owner-Zsh und ein separates nicht blockierendes Logo-/Status-Pane.
Neue `|`-/`-`-Splits starten erneut denselben Owner-Shell-Einstieg. Nur dieser Shell-Kindprozess laedt die private Capability in sein Prozess-Environment und erhaelt `ROBA_CONTROL_TOKEN`, `ROBA_DAEMON=id:default` sowie
`ROBA_CONTROL=id:default`. tmux-Environment, Optionen, Pane-Titel, Status, argv und Dokumentation
bleiben secretfrei.

Die Owner-Shell besitzt eigenes `ZDOTDIR`, History, Completion fuer `dix-cockpit`, `dix-roba-cli`
und `roba-ctl` sowie einen sichtbaren Prompt mit `cockpit` und dem konkreten Sessionnamen.
Navigation, Resize, vi-Copy-Mode, Reload und Clipboardadapter bleiben erhalten. Owner-Artefakt und
Zsh-Dateien verwenden Modus `0600`, private Verzeichnisse `0700`.

Nuetzliche Checks in der Owner-Shell:

```sh
dix-roba-cli daemon status
roba-ctl ctx list
```

Das Status-Pane rendert das gewaehlte gepruefte PNG mit Chafa und faellt andernfalls auf Text
zurueck. Eine reale visuelle Terminalabnahme bleibt von der automatischen Verifikation getrennt.
