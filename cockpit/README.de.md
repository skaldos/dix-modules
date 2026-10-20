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

## Optionale Master-UI

Die Master-UI ist eine explizite optionale Schicht ueber der privilegierten Runtime. Zuerst wird
die Basis-Runtime installiert, danach die UI:

```sh
./cockpit/integrations/install
./cockpit/integrations/install-ui

dix-cockpit-ui start --session dix --logo dix
```

Der zweite Installer ergaenzt VisiData 3.4 und baut eine getrennte statische Sourceprojektion aus
einer expliziten Allowlist samt `dix-cockpit-ui` und internem Helper
`dix-cockpit-master-workbench`. Eine Wiederholung ersetzt diese private Projektion und entfernt
stale Dateien. Der Basis-Installer wird weder verbreitert noch ersetzt; seine drei
Runtime-Launcher bleiben VisiData-frei.

`dix-cockpit-ui start` verwendet den bestehenden Cockpit-Lifecycle, vervollstaendigt das
vorhandene `control`-Window und attached. Das Window enthaelt Logo/nicht geheimen Status,
Owner-Shell und den groessten Pane fuer den generischen ROBA-Loom-Workbench. Jeder Pane besitzt
einen sichtbaren Titel. Ein wiederholter Start fokussiert den laufenden Workbench. Endete dessen
Prozess, bleiben Pane und Fehler sichtbar; erst der naechste explizite UI-Start respawnt dieselbe
Rolle statt ein Duplikat zu erzeugen. Detach laesst alle Prozesse laufen. Fuer Lifecycle-
Operationen bleiben `dix-cockpit attach|status|stop|reset` zustaendig; die UI dupliziert sie
bewusst nicht.

Der Master-Helper validiert das lebende Owner-Artefakt im eigenen Prozess und baut dort die
Loom-Connection. Das Control-Token gelangt nie in argv, Seed-Datei, tmux-Environment, Optionen,
Rollenmetadaten oder Titel. Innerhalb dieses persoenlichen Owner-Workbenches darf es bewusst
sichtbar und bearbeitbar sein. Enter inspiziert nur die gewaehlte ObjectReference und oeffnet
einen lokalen Draft. Space ist der einzige Provider-Ausfuehrungsweg und behaelt die vorhandene
Bestaetigung. Providerfehler erhalten die Workbench-Session.

tmux behaelt die oben beschriebene isolierte Tastenoberflaeche: `C-a` (oder `C-b`) ist der Prefix,
`h/j/k/l` navigiert Panes, `C-h`/`C-l` wechselt Windows, `H/J/K/L` aendert die Groesse und
`Escape` startet den vi-Copy-Mode. Die konfigurierten Copy/Paste-Adapter bevorzugen das
System-Clipboard und fallen auf den privaten tmux-Buffer zurueck. Locator-Katalog, externes
Zielwindow, Datei-Import/-Export, Save, Sync und Runner sind nicht Teil dieser UI.

## Optionale lokale TOML-Value-Workbench

Die lokale TOML-Workbench ist bewusst vom privilegierten Runtime-Installer getrennt. Sie
benoetigt Python 3.12, `uv`, VisiData 3.4, diesen vollstaendigen `dix-modules`-Checkout und das
gleiche zentrale DIX-Environment. Eine laufende Cockpit-Session, ROBA, DIX Control, ein Katalog
oder ein Loom-Provider sind nicht erforderlich.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; das ist der Default
./cockpit/integrations/install-workbench

dix-cockpit-toml-workbench --file ./value.toml --logo dix
# alternativ: --logo roba
```

Der optionale Installer erzeugt eine frische private Sourceprojektion nur aus dem TOML-Dateileser,
der lokalen Value-Workbench, einer Cockpit-Application und beiden Logos. Er installiert
ausschliesslich `dix-cockpit-toml-workbench`. Eine Wiederholung entfernt stale Dateien aus dieser
Projektion. `cockpit/integrations/install`, seine drei privilegierten Launcher, das tmux-Layout und
die Owner-Shell werden nicht geaendert.

Der explizite Pfad wird relativ zum Prozess-CWD interpretiert, sofern er nicht absolut ist. Die
Quelle wird exakt einmal als UTF-8-TOML gelesen. Die Workbench erhaelt einen abgeloesten nativen
Wert; Pfadmetadaten werden nicht in diesen Wert injiziert. Quelle und Quellverzeichnis werden nie
beschrieben. Das Prozessende verwirft Draft und lokales Register. Dieser Command besitzt kein
Save, Reload, Recovery, Sync, Import/Export und keine Providerausfuehrung.

### Tasten der lokalen Workbench

| Taste | Wirkung |
| --- | --- |
| Enter | In das gewaehlte Mapping oder die Liste drillen; nie extern ausfuehren |
| e | Gewaehlten Skalar durch exakt ein TOML-Literal ersetzen |
| a | Mapping-Eintrag anlegen oder einen TOML-Wert an die aktuelle Liste anhaengen |
| i | TOML-Wert vor dem gewaehlten Listeneintrag einfuegen |
| r | Gewaehlten Mapping-Key ohne Ueberschreiben eines anderen Keys umbenennen |
| d | Gewaehlten Mapping-/Listeneintrag bestaetigt loeschen |
| y | Gewaehlten vollstaendigen Teilbaum tief in das sitzungslokale Register kopieren |
| p | Gewaehlten Teilbaum durch eine tiefe Kopie des Registers ersetzen |
| A | Register in das aktuelle Mapping einfuegen oder an die aktuelle Liste anhaengen |
| I | Register vor dem gewaehlten Listeneintrag einfuegen |
| B | Gewaehltes DIX-/ROBA-Logo erneut anzeigen |
| q | In VisiData zurueck/beenden; beim Prozessende werden alle lokalen Aenderungen verworfen |

Der Sheet-Titel zeigt immer `clean` oder `DIRTY` und `empty` oder `set` fuer das lokale Register.
Eine feste zweiteilige Kopfzeile zeigt Branding und Quelldatei, den live aus dem Draft gelesenen
Dirty-/Registerzustand sowie den aktuellen Breadcrumb von `value` bis zum sichtbaren Mapping-Key
oder Listenindex. Sie ist keine selektierbare Datenzeile.
Ungueltiges TOML, fehlende Pfade, falsche Container, ungueltige Indizes, Key-Kollisionen, ein
leeres Register und ein abgebrochenes Loeschen lassen Draft und Register unveraendert. Native
TOML-Dates, Times, Datetimes, Sonderfloats sowie verschachtelte Mappings/Listen bleiben native
Werte.
