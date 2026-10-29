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
vorhandene `control`-Window und attached. Seine vier besessenen Rollen sind Logo/nicht geheimer
Status (oben links), breiter ROBA-Loom (oben rechts), gestagte Store-Workbench (unten links) und
Owner-Shell (unten rechts). Jeder Pane besitzt
einen sichtbaren Titel. Ein wiederholter Start fokussiert den laufenden Workbench. Endete dessen
Prozess, bleiben Pane und Fehler sichtbar; erst der naechste explizite UI-Start respawnt dieselbe
Rolle statt ein Duplikat zu erzeugen. Detach laesst alle Prozesse laufen. Fuer Lifecycle-
Operationen bleiben `dix-cockpit attach|status|stop|reset` zustaendig; die UI dupliziert sie
bewusst nicht.

Der Master-Helper validiert das lebende Owner-Artefakt im eigenen Prozess und baut dort die
Loom-Connection. Das Control-Token gelangt nie in argv, Seed-Datei, tmux-Environment, Optionen,
Rollenmetadaten oder Titel. Innerhalb dieses persoenlichen Owner-Workbenches darf es bewusst
sichtbar und bearbeitbar sein. Im oberen rechten Loom inspiziert Enter nur die gewaehlte ObjectReference und oeffnet
einen lokalen Draft. Space ist der einzige Provider-Ausfuehrungsweg und behaelt die vorhandene
Bestaetigung. Providerfehler erhalten die Workbench-Session.

tmux behaelt die oben beschriebene isolierte Tastenoberflaeche: `C-a` (oder `C-b`) ist der Prefix,
`h/j/k/l` navigiert Panes, `C-h`/`C-l` wechselt Windows, `H/J/K/L` aendert die Groesse und
`Escape` startet den vi-Copy-Mode. Die konfigurierten Copy/Paste-Adapter bevorzugen das
System-Clipboard und fallen auf den privaten tmux-Buffer zurueck. Automatische Zielerzeugung, Datei-Import/-Export, Save, Sync und Runner sind nicht Teil
des Master-Looms; der getrennte Read-only-Store-Katalog ist unten beschrieben.

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

## Gestagte Store-Workbench (UP-066 / UP-067)

Nach einem Source-Update `./cockpit/integrations/install-ui` erneut ausfuehren. Der Installer
liefert auch den internen Helper `dix-cockpit-store-workbench --session dix --logo dix`.
Der normale Einstieg bleibt `dix-cockpit-ui start --session dix --logo dix`. Start ist idempotent:
er vervollstaendigt fehlende eigene Rollen, fokussiert den vorhandenen Loom und respawnt bewusst
beendete Loom-/Store-Panes. Fremde oder mehrdeutige Rollen werden nie adoptiert. Detach laesst
alle vier Prozesse weiterlaufen.

Der **untere linke Store-Pane** ist jetzt das fuehrende lokale Registrierungs-/Editierinterface:

| Taste | Wirkung ausschliesslich in diesem Store-Pane |
| --- | --- |
| :n | Neuer Provider-Draft; ein Provider direkt, mehrere mit expliziter Auswahl |
| Enter auf Katalogzeile | Lokale Definition oeffnen, nicht das Ziel |
| Enter auf Container | Innerhalb desselben Drafts drillen |
| Enter auf atomarem value | Nativer Inline-Zelleditor am Zellort, kein Footer-TOML-Prompt |
| Enter / Esc im Editor | Lokal annehmen / nur diese Zellbearbeitung abbrechen |
| :w / Ctrl+S | Vollstaendigen Store validieren und genau einmal im lokalen Katalog speichern |
| q | Parent; am Katalog-Root aktiv bleiben |
| :r / Ctrl+R | Draft schuetzen, danach Katalog neu laden |
| :q | Draft schuetzen, danach diese Store-Workbench bewusst beenden |
| :wq | Speichern; nur bei Erfolg den Pane verlassen |
| :q! | Draft bewusst ohne Nachfrage verwerfen und Pane verlassen |
| h j k l / Pfeile | Native Zeilen-/Spaltennavigation |
| PageUp / PageDown | Seitenweise bewegen |
| gg / G | Erste / letzte Zeile |

`:` oeffnet ausschliesslich den Cockpit-Prompt fuer `n`, `w`, `q`, `wq`, `q!`, `r`.
Die Tokens werden getrimmt; leere oder unbekannte Tokens zeigen eine lokale Meldung und tun
sonst nichts. Keine Parameter, Shellbefehle, Regex- oder Ex-Sprache. Der Store importiert
VisiData **3.4** vollstaendig, prueft die SettingsMgr-/Command-/Input-Grenze vor curses,
leert seine gesamte prozesslokale Binding-Registry und registriert nur diese 17 Tasten.
Der kompakte sheet-lokale rechte Status reserviert Eingabebreite fuer Prompts im geteilten Pane.
Bei inkompatibler Version oder Registry bricht der Start mit Exitcode 2 und einer festen,
credentialfreien Meldung ab. Menue, `i`, `-`, Datei-Save und allgemeine Spreadsheet-Shortcuts
bleiben unerreichbar. **`a`, `z Ctrl+S` und `gq` haben keine Kompatibilitaetsaliase.**

Strings brauchen keine Quotes; Tippen ersetzt den initialen Zellwert (natives VisiData-Verhalten).
Vorhandene Integer/Floats behalten ihren Typ; Floats muessen endlich sein. Booleans akzeptieren
`true` oder `false` (Gross-/Kleinschreibung egal), nicht `yes`/`no` oder `0`/`1`. Ungueltige Eingabe
bewahrt den alten Wert und zeigt einen lokalen Fehler. Der einzige ausgelieferte ROBA-Draft hat
kein Boolean-Feld; diese Typgrenze ist ueber eine reine Terminal-Testfixture belegt, nicht ueber
einen zusaetzlich installierten Provider.

Angenommene Zellen aendern nur den Draft und seinen sichtbaren **DIRTY**-/Modified-Marker. Vor
`:w` oder **Ctrl+S** erfolgt kein Katalogaufruf. Neuanlagen verwenden
ein `create`, bestehende Definitionen ein `update`. Doppelte IDs, unbekannte Provider, ungueltige
Definitionen oder lokale Transportfehler bewahren Baseline und Katalog. Derselbe dirty Draft
bleibt fuer Korrektur und erneuten Commit erhalten.

Beim Verlassen dirty Drafts (Root-Zurueck, New/Wechsel, Reload oder expliziter Exit) fragt
**Save / Discard / Cancel**: `s` speichert einmal und geht nur bei Erfolg weiter; `d` verwirft ohne
Schreiben; `c` oder Esc bleibt im selben Draft. Navigation zwischen Containern fragt nie.
Credentials duerfen im persoenlichen Editor bewusst sichtbar sein; kein Ziel wird kontaktiert
und kein Credential gelangt in Prozessargumente, tmux-Metadaten/-Titel, Breadcrumbs, Status oder
normale Fehlerlogs. Der Katalog bleibt fluechtig: Stop/Start oder Reset verwirft ihn.
„Persistenter Pane“ bedeutet keine Dateipersistenz.

Der unten beschriebene abgeloeste `zN`-/`zE`-/`zC`-Draftflow bleibt kompatibel vorhanden, ist aber
nicht mehr der fuehrende Store-Editierweg.
VisiDatas in der Mainloop fest behandeltes `Ctrl+Q` liegt ausserhalb der Binding-Registry.
Der Store-Prozess prueft deshalb nach Rueckkehr aus `vd.run()` seinen Draft: Bei dirty State folgt
nach Curses-Ende dieselbe Save/Discard/Cancel-Auswahl als normaler Terminalprompt. Cancel oder
fehlgeschlagenes Save kehrt zum selben Draft/Pfad/Cursor zurueck; Save oder Discard beendet
bewusst. Das patcht VisiData nicht und beeinflusst keine andere Workbench. Erzwungene Zerstoerung
durch OS, Prozess-Kill oder Terminalende ist kein geschuetzter Navigationsbefehl. Read-only-Dual-Browser und oberer rechter breiter
ROBA-Loom behalten ihre bisherigen Tasten. Nur der Master-Loom startet jetzt direkt ohne
Enter-Vorspann; Logo/Status bleiben im eigenen Pane sichtbar. Andere Workbenches behalten
Branding und Startvertrag. VisiDatas globale Quit-Semantik wird nicht gepatcht.

## Read-only Stores (UP-065)

Nach einem Update `./cockpit/integrations/install-ui` erneut ausfuehren. Der Installer liefert
auch den internen Helper `dix-cockpit-store-browser`; die Basisruntime bleibt VisiData-frei.
Master wie oben starten. In dessen VisiData-Pane oeffnet `zN` (`cockpit-new-store` in der
Command-Hilfe) **New Store**, `zS` (`cockpit-open-stores`) oeffnet/fokussiert das stabile
`stores`-Window. Diese prozesslokalen Commands aendern den generischen Loom nicht. Alternativ
im Owner-Terminal oder einem externen aktivierten Terminal:

```sh
dix-cockpit-ui stores --session dix --logo dix
```

Voraussetzung ist ein gesundes, besessenes Cockpit. Ausserhalb tmux wird attached, innerhalb das
Window fokussiert. Es besitzt genau zwei unabhaengige Browser, **Stores A** und **Stores B**.
Die oben beschriebene isolierte tmux-Prefix-/Pane-/Window-Navigation bleibt gueltig. Erneutes
Oeffnen fokussiert laufende Panes; beendete Panes bleiben sichtbar und werden erst beim bewussten
Oeffnen respawnt. Detach erhaelt den Raum; nur `dix-cockpit stop|reset` raeumt die Runtime auf.

### Vorhandenen Zugang registrieren, kein neues Ziel erzeugen

1. Ziel-Context, Instance, Token, Socket und Grant werden vorher separat im administrativen
   Terminal erzeugt. New Store erzeugt oder repariert keine dieser Ressourcen.
2. `zN` im Master oder `zN` im Browser druecken. `roba` waehlen (einziger Provider); Enter nimmt
   den vorbelegten Provider. Ein abgeloester lokaler Draft mit `store_id`, `provider` und
   `connection` oeffnet sich. Das Ziel wird nicht kontaktiert.
3. Mit Enter in `connection` drillen, mit `e` Skalare als **TOML-Literale** bearbeiten, etwa
   `"project"`, `"unix:/absoluter/vorhandener/ctx.sock"`, `"hier-vorhandenes-token-einfuegen"`,
   `5.0`. Am Root einen nicht leeren `store_id` setzen. Default ist die vorhandene kanonische
   direkte Context-Variante: `context_id`, `context_locator`, `token`, `timeout`. Mit `a`
   `instance_id` fuer eine vorhandene Instance ergaenzen. Fuer einen vorhandenen Capability-Socket
   das Feld `token` mit `d` entfernen und den direkten Socket-Locator verwenden. Der Provider
   akzeptiert auch die vorhandenen vollstaendigen DIX-ROBA-Control-Capability-Varianten, kein
   alternatives Credentialschema.
4. Auf beliebiger Drafttiefe `zC` (`commit-local-definition`) druecken und einmal bestaetigen.
   Nur die gesamte lokale Definition wird im privaten Cockpit-Katalog abgelegt. Mit `q` zurueck;
   den Browser-Root mit `Ctrl-R` neu laden. Schliessen ohne `zC` verwirft die Aenderungen.
5. Erst Enter auf dem Store liest bewusst das Ziel. Fehlende, offline oder unberechtigte Ziele
   scheitern hier, nicht beim Registrieren. Mit `zB` zurueck, lokalen Zugang mit `zE` korrigieren,
   dann neu laden.

| Browsertaste | Wirkung |
| --- | --- |
| Enter | Gewaehlten Container lesen oder Wert inspizieren; keine Providermutation |
| zB | Parent; vom Store-Root zum virtuellen Root |
| zU | Virtueller Root |
| Ctrl-R | Nur diesen Pane neu laden; auch gemeinsamen Katalog aktualisieren |
| zN | Neuer lokaler Store ueber Providerwahl und abgeloesten Draft |
| zE | Lokale Store-Definition bearbeiten; zC committet bewusst |
| zR | Nur lokale Registrierung umbenennen |
| zX | Nur lokale Registrierung bestaetigt entfernen |
| q | VisiData zurueck/beenden; kein Daemoncleanup |

Beide Browser lesen denselben lebenden Katalog; Auswahl, Cursor, Pfad und Fehler bleiben aber
pane-lokal. Die feste Kopfzeile zeigt Breadcrumb oder sichtbaren Fehler. Auch leere/fehlerhafte
Zustaende haben einen Rueckweg nach `/`. ROBA exponiert nur Context-Metadaten, lesbare Instances,
Keys und Werte. Control-Zugriff impliziert **kein** Context-Owner-Credential; fuer dessen Daten
einen separaten Context-Zugang registrieren. Ein Token nur mit Instance-Read sieht nur diese
lesbaren Ressourcen. Create, Delete, Write, Token, Socket, Grant und Management sind auch mit
manipulierten Node-IDs unerreichbar. Der Master behaelt bewusst seinen breiten Owner-Loom.

Der Katalog ist fluechtiger privater ROBA-State mit serialisierten Aenderungen pro Cockpit-Session.
Andere Prozesse derselben Session sehen bewusste Commits beim Reload; andere Sessions nicht.
Lokales Edit/Rename/Remove kontaktiert das externe Ziel nie und loescht/widerruft dort nichts.
Vollstaendiges Stop/Start oder Reset verwirft den Katalog. Es gibt weder Dateipersistenz,
Autosave, Snapshot, Import/Export, Transfer, zweiten Provider, Sync noch Runner.

Credentials duerfen im persoenlichen Owner-Draft angezeigt, bearbeitet und kopiert werden,
gelangen aber nicht in argv, tmux-Metadaten/-Environment/-Titel, Breadcrumbs, Status oder normale
Fehlerlogs. Browserhelper erhalten nur Session/Logo/Seite und beziehen die private Capability
innerhalb ihres Prozesses. Terminalaufzeichnungen koennen bewusst angezeigte Tokens trotzdem
erfassen: kurzlebige Testcredentials nutzen, Aufzeichnungen privat halten und vor Weitergabe
pruefen/bereinigen.
