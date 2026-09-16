# `skaldos/sway`

Topologiebewusste Sway-Fenstergruppen-Navigation, mit DIX komponiert und ueber ROBA koordiniert.

[English](README.md) · [Repository-Ueberblick](../README.de.md) ·
[DIX](https://github.com/skaldos/dix) · [ROBA](https://github.com/skaldos/roba)

> **Public Alpha:** Das Modul ist bereits in einem realen Sway-Workflow nuetzlich, Einrichtung und
> Source-Vertraege koennen sich aber noch aendern. Es wird als Source und nicht als Python-Paket
> geliefert.

Die Dokumentation ist auf Englisch und Deutsch verfuegbar. Ausgelieferte Befehlsnamen, Prompts und
maschinennahe Fehlermeldungen sind englisch.

## Was es macht

Mit `skaldos/sway` kann ein normales gerichtetes Sway-Binding entweder nativ oder gegen eine
ausgewaehlte Gruppe von Fenster-Container-IDs arbeiten:

```text
Sway IPC
+ ROBA coordination state
+ DIX compositions/applications
+ fixed low-latency keybindings
= topology-aware window-group navigation
```

Sway bleibt die Richtungsautoritaet. Die Gruppennavigation fuehrt zuerst den nativen Befehl
`focus left|right|up|down` aus. Ein direkter erlaubter Treffer wird sofort uebernommen. Wenn Sway
in einen Stacked- oder Tabbed-Branch wechselt, dessen sichtbares Leaf nicht in der aktiven Gruppe
liegt, waehlt das Modul anhand einer minimalen Sway-Topologie ein erlaubtes lebendes Leaf in diesem
Branch. Es ersetzt Sway nicht durch einen geometriebasierten Window Manager.

## Verantwortungslandkarte

Das System haelt unterschiedliche Zustaende bewusst unter unterschiedlicher Ownership:

| Owner | Daten oder Verhalten |
| --- | --- |
| Sway | Live-Tree, Fokus, Container-IDs und native Richtungssemantik. |
| DIX | Explizites Laden und Komponieren von Compositions und Applications. |
| ROBA | Ephemere geteilte Koordination: Gruppennamen und Name der aktiven Gruppe. |
| Group-Application | Privates JSON-Mapping von Gruppennamen auf Sway-`con_id`-Werte. |
| Navigationsprojektionen | Eine Zeile aktiver lebender IDs und ein Routingwert `basic`/`group`. |
| Nutzer | Prozess-Lifecycle, lokale Pfade, Dateirechte und Keybindings. |

ROBA **persistiert nichts**. Das private JSON und die beiden Projektionsdateien sind normale lokale
Dateien des konfigurierten Modul-Workflows; sie sind keine ROBA-Persistenz. Sway-Container-IDs sind
Runtime-Werte und koennen nach dem Beenden einer Anwendung oder einem Sway-Neustart veraltet sein.

## Voraussetzungen

- Linux mit Sway und einem funktionierenden `SWAYSOCK`;
- Python 3.12 oder neuer;
- [`uv`](https://docs.astral.sh/uv/);
- Git;
- Wofi nur fuer die optionalen Auswahlskripte.

Das Modul besitzt exakt eine direkte Sway-Abhaengigkeit in
[`requirements.txt`](requirements.txt): `i3ipc==2.2.1`. DIX besitzt sie bewusst nicht.

## 1. Source-Struktur klonen

In einem leeren Verzeichnis beginnen:

```sh
mkdir -p skaldos-sway-showcase
cd skaldos-sway-showcase
git clone https://github.com/skaldos/roba.git roba
git clone https://github.com/skaldos/dix.git dix

export SKALDOS_WORKSPACE=$PWD
export DIX_ROOT=$SKALDOS_WORKSPACE/dix
```

Den externen Checkout nicht vor dem initialen DIX-Sync unter `dix/modules` ablegen. Dort bereits
vorhandene Verzeichnisse sind Inputs einer lokal gebauten DIX-Distribution. Wird zuerst der
committete DIX-Source vorbereitet, bleibt diese Distribution auf DIX-eigene Module begrenzt; der
externe Checkout kommt danach als Source-Consumer hinzu.

## 2. DIX-Umgebung vorbereiten

DIX verweist in dieser Struktur bereits auf den benachbarten Source `../roba`. Die deklarierten
Extras synchronisieren und danach die Sway-eigenen Requirements in dieselbe Umgebung installieren:

```sh
cd "$DIX_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba

git clone https://github.com/skaldos/dix-modules.git "$DIX_ROOT/modules/skaldos"
export SWAY_ROOT=$DIX_ROOT/modules/skaldos/sway

uv pip install --python "$DIX_ROOT/.venv/bin/python" -r "$SWAY_ROOT/requirements.txt"
```

Der abschliessende Dependency-Installationsbefehl ist bewusst sichtbar. Kein Import-Hook
installiert `i3ipc` stillschweigend.

Die resultierende Form ist beabsichtigt:

```text
$SKALDOS_WORKSPACE/
├── roba/
└── dix/
    └── modules/
        ├── dix/{cli,state,roba}
        └── skaldos/sway
```

Zwischen den Repositories existiert keine Git-Submodule-, Package-Manager- oder Discovery-
Beziehung. DIX erhaelt `skaldos/sway` als expliziten Sourcepfad mit der Modul-ID `skaldos/sway`.

## 3. Lokale Sway-State-Dateien festlegen

Ein privates Verzeichnis verwenden und alle drei Grenzen konsistent exportieren:

```sh
export SKALDOS_SWAY_STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/skaldos/sway
export SKALDOS_SWAY_GROUP_STATE_FILE=$SKALDOS_SWAY_STATE_DIR/groups.json
export SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$SKALDOS_SWAY_STATE_DIR/active-members
export SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$SKALDOS_SWAY_STATE_DIR/navigation-target
mkdir -p "$SKALDOS_SWAY_STATE_DIR"
```

- `groups.json` ist private Group-Ownership und enthaelt Namen samt gespeicherten `con_id`-Listen.
- `active-members` ist eine schmale, newline-terminierte Liste fuer den Navigations-Hot-Path.
- `navigation-target` enthaelt exakt `basic` oder `group` plus Newline.

`groups.json` ist lokaler Nutzerzustand. Die Projektionsdateien sind ersetzbare Ausgaben und
duerfen nicht in ungueltige Werte editiert werden.

## 4. DIX-ROBA-CLI bauen und installieren

Der Management-Einstieg benoetigt einen laufenden ROBA-Daemon, die DIX-Control-Registry und einen
verwalteten Context. Die committete Typer-Application einmal bauen und danach einen transparenten
lokalen Befehl installieren:

```sh
export DIX_LAUNCHER_HOME=${XDG_DATA_HOME:-$HOME/.local/share}/dix/launchers
mkdir -p "$DIX_LAUNCHER_HOME" "$HOME/.local/bin"
"$DIX_ROOT/.venv/bin/python" -m dix.bootstrap build \
  "$DIX_ROOT/examples/launchers/dix_roba.toml" \
  --output "$DIX_LAUNCHER_HOME/dix-roba.py" \
  --replace

cat > "$HOME/.local/bin/dix-roba" <<EOF
#!/bin/sh
exec "$DIX_ROOT/.venv/bin/python" "$DIX_LAUNCHER_HOME/dix-roba.py" "\$@"
EOF
chmod 0755 "$HOME/.local/bin/dix-roba"
export PATH=$HOME/.local/bin:$PATH
dix-roba --help
```

Der erzeugte Launcher ist die echte Typer-Application `dix/roba/cli` mit expliziten
Modul-Sources. Die lokale Datei `dix-roba` bindet diesen Launcher nur an DIX' Python-Umgebung.
Keine der beiden Dateien ist ein Daemon oder fuehrt Discovery aus. Nach dem Verschieben des
DIX-Checkouts beide neu bauen.

## 5. ROBA konfigurieren, starten und `skaldos-sway` erzeugen

Ohne Overrides behaelt DIX die belegte Daemon-ID `default`, den Runtime-Root `~/.roba/runtime` und
den Log-Root `~/.roba/logs`. Fuer XDG-orientierte lokale Pfade vor jedem DIX-ROBA-Consumer einen
gemeinsamen DIX-Vertrag setzen:

```sh
if [ -n "${XDG_RUNTIME_DIR:-}" ]; then
  export DIX_ROBA_RUNTIME_ROOT=$XDG_RUNTIME_DIR/dix/roba
else
  export DIX_ROBA_RUNTIME_ROOT=${XDG_STATE_HOME:-$HOME/.local/state}/dix/roba/runtime
fi
export DIX_ROBA_LOGS_ROOT=${XDG_STATE_HOME:-$HOME/.local/state}/dix/roba/logs

dix-roba managed start
dix-roba control create_context \
  --context_id skaldos-sway
dix-roba daemon status
```

`managed start` startet ROBA und bootstrapt den DIX-Control-Context. `create_context` erzeugt danach
den Modul-Context und dessen Manager-Socket. Diese Befehle geben capability-tragende Ergebnisdaten
aus; Tokens gehoeren nicht in Dokumentation, Logs oder Tickets.

Die beiden Werte duerfen stattdessen beliebige absolute nutzereigene Pfade sein:

```sh
export DIX_ROBA_RUNTIME_ROOT=/absoluter/pfad/zur/roba-runtime
export DIX_ROBA_LOGS_ROOT=/absoluter/pfad/zu/roba-logs
```

Jeder getrennt gestartete DIX-Consumer, einschliesslich `skaldos-sway-json` und der Wofi-Helfer,
muss dieselben beiden Werte erben. Benannte Typer-Parameter wie `--runtime_root` und `--logs_root`
ueberschreiben sie fuer einen Aufruf; dann benoetigen aber alle zusammengehoerigen Aufrufe dieselben
expliziten Werte. Kein nicht expandiertes literales `~` in exportierten oder benannten
Custom-Pfaden verwenden. Den Runtime-Root kurz genug fuer das Unix-Socket-Pfadlimit der Plattform
halten.

`create_context` nicht wiederholt gegen einen bereits existierenden Context ausfuehren. Ein
Duplikat ist ein sichtbarer Fehler und kein Attach-Vorgang.

## 6. Die zwei transparenten Wrapper installieren

Die Wrapper lokalisieren nur den Source-Tree und starten den committeten Einstieg mit DIX' Python:

```sh
mkdir -p "$HOME/.local/bin"
ln -sfn "$SWAY_ROOT/integrations/bin/skaldos-sway-nav" \
  "$HOME/.local/bin/skaldos-sway-nav"
ln -sfn "$SWAY_ROOT/integrations/bin/skaldos-sway-json" \
  "$HOME/.local/bin/skaldos-sway-json"
export PATH=$HOME/.local/bin:$PATH
```

Sie leiten die dokumentierte Struktur aus dem realen Symlink-Ziel ab. Fuer eine abweichende
Source-Struktur koennen absolute Werte fuer `SKALDOS_DIX_ROOT` und `SKALDOS_SWAY_ROOT` gesetzt
werden. Kein nicht expandiertes literales `~` in diesen Variablen verwenden.

Die Wrapper starten ROBA niemals. `skaldos-sway-json` ist der breite DIX-/ROBA-Managementpfad;
`skaldos-sway-nav` ist der direkte, dependency-arme Navigationspfad.

## 7. Gruppen verwalten

Diese Befehle innerhalb einer echten Sway-Session mit den drei exportierten State-Variablen
ausfuehren.

Eine Gruppe erzeugen und auflisten:

```sh
skaldos-sway-json create work
skaldos-sway-json list-lines
```

Ein Fenster fokussieren, hinzufuegen und die Gruppen dieses fokussierten Fensters anzeigen:

```sh
skaldos-sway-json add work
skaldos-sway-json memberships-lines
```

Weitere Fenster fokussieren und jeweils `add work` wiederholen. Ein Fenster darf in mehreren
Gruppen liegen.

Eine Gruppe aktivieren und ihren aktiven Namen anzeigen:

```sh
skaldos-sway-json select work
skaldos-sway-json current
```

Das aktuell fokussierte Fenster aus einer Gruppe entfernen:

```sh
skaldos-sway-json remove work
```

Das Routing auf native/Basic-Navigation zuruecksetzen, ohne die private Gruppe zu loeschen:

```sh
skaldos-sway-json deactivate
```

`create`, `add`, `remove`, `select` und `deactivate` sind explizite Mutationen. `list-lines`,
`memberships-lines` und `current` sind zeilenorientierte Chooser-/Leseausgaben.

## 8. Navigation direkt testen

Ein explizites Target umgeht die Routingdatei, ohne sie zu veraendern:

```sh
skaldos-sway-nav --target basic right
skaldos-sway-nav --target group left
```

Ohne `--target` liest der Einstieg `navigation-target`; fehlt die Datei, ist der Default `basic`:

```sh
skaldos-sway-nav right
```

Die Navigation schreibt genau ein kompaktes JSON-Ergebnis. Das Group-Target benoetigt eine gueltige
Active-Member-Projektion. Der direkte Prozess importiert bewusst weder Typer, Click, ROBA, HTTPX
noch Pydantic.

## 9. Optionale Wofi-Befehle

Mit `skaldos-sway-json` auf `PATH` und denselben exportierten State-Variablen:

```sh
"$SWAY_ROOT/integrations/wofi/select"
"$SWAY_ROOT/integrations/wofi/add"
"$SWAY_ROOT/integrations/wofi/remove"
```

Die Menues fuer vorhandene Eintraege starten Wofi mit `--no-custom-entry`. Enter auf der initial
hervorgehobenen Zeile uebernimmt diese deshalb ohne vorherige Cursorbewegung. Nur der getrennte
Dialog fuer einen neuen Gruppennamen erlaubt freie Texteingabe.

Die Aktionszeilen lauten `[No active group]` und `[+ New group]`. Add und Remove verwenden die
Prompts `Add window to group` und `Remove window from group`; die freie Eingabe eines Gruppennamens
verwendet `New group name`.

`SKALDOS_SWAY_MANAGEMENT`, `SKALDOS_SWAY_WOFI` oder `SKALDOS_SWAY_WOFI_NAME` nur ueberschreiben,
wenn der Ersatzbefehl bewusst selbst verantwortet wird. Diese Variablen sind Shell-Command-
Grenzen und keine DIX-API.

## 10. Sway-Bindings hinzufuegen

Das vollstaendige gepflegte Fragment liegt unter
[`integrations/sway/config`](integrations/sway/config). Es in die Sway-Konfiguration kopieren und
`/home/YOU` sowie `path/to/workspace` durch absolute Werte ersetzen:

```text
set $skaldos_home /home/YOU
set $skaldos_sway $skaldos_home/path/to/workspace/dix/modules/skaldos/sway
set $skaldos_state $skaldos_home/.local/state/skaldos/sway

set $skaldos_nav env SKALDOS_SWAY_GROUP_STATE_FILE=$skaldos_state/groups.json SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$skaldos_state/active-members SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$skaldos_state/navigation-target $skaldos_home/.local/bin/skaldos-sway-nav
set $skaldos_manage env SKALDOS_SWAY_GROUP_STATE_FILE=$skaldos_state/groups.json SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$skaldos_state/active-members SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$skaldos_state/navigation-target SKALDOS_SWAY_MANAGEMENT=$skaldos_home/.local/bin/skaldos-sway-json

exec_always --no-startup-id mkdir -p $skaldos_state

bindsym $mod+h exec --no-startup-id $skaldos_nav left
bindsym $mod+j exec --no-startup-id $skaldos_nav down
bindsym $mod+k exec --no-startup-id $skaldos_nav up
bindsym $mod+l exec --no-startup-id $skaldos_nav right

bindsym $mod+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/select
bindsym $mod+Shift+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/add
bindsym $mod+Ctrl+g exec --no-startup-id $skaldos_manage $skaldos_sway/integrations/wofi/remove
```

Ein Export in einer interaktiven Shell aendert die Umgebung eines bereits laufenden Sway-Prozesses
nicht rueckwirkend. Bei Custom-ROBA-Roots entweder Sway mit beiden `DIX_ROBA_*`-Werten starten oder
absolute Werte in den Management-Befehl des Fragments aufnehmen:

```text
set $skaldos_roba_runtime /absoluter/pfad/zur/roba-runtime
set $skaldos_roba_logs /absoluter/pfad/zu/roba-logs
set $skaldos_manage env DIX_ROBA_RUNTIME_ROOT=$skaldos_roba_runtime DIX_ROBA_LOGS_ROOT=$skaldos_roba_logs SKALDOS_SWAY_GROUP_STATE_FILE=$skaldos_state/groups.json SKALDOS_SWAY_ACTIVE_MEMBERS_FILE=$skaldos_state/active-members SKALDOS_SWAY_NAVIGATION_TARGET_FILE=$skaldos_state/navigation-target SKALDOS_SWAY_MANAGEMENT=$skaldos_home/.local/bin/skaldos-sway-json
```

Bindings waehlen, die nicht mit der eigenen Konfiguration kollidieren. Danach neu laden und einen
Basic-Smoke-Test ausfuehren:

```sh
swaymsg reload
skaldos-sway-json list-lines
skaldos-sway-nav --target basic right
```

Der letzte Befehl verschiebt den Fokus. Sobald eine Gruppe lebende Mitglieder hat, kann sie
ausgewaehlt und ueber die festen Bindings getestet werden.

## Herunterfahren und Neustart

Den Default-Daemon explizit stoppen:

```sh
dix-roba daemon stop
```

Alle ROBA-Contexts und Koordinationszustaende verschwinden. Privates JSON und Projektionsdateien
bleiben bestehen, weil sie separate lokale Dateien und kein ROBA-State sind.

Nach einem reinen ROBA-Neustart:

```sh
dix-roba managed start
dix-roba control create_context \
  --context_id skaldos-sway
skaldos-sway-json deactivate
skaldos-sway-json select work
```

Die letzten zwei Aufrufe publizieren Koordination und Projektionen erneut aus dem privaten
Gruppenzustand. Nach einem Sway-Neustart koennen gespeicherte `con_id`-Werte veraltet sein; die
Mitgliedschaft gegen die neuen lebenden Fenster neu aufbauen, statt IDs als persistente
Identitaeten zu behandeln.

## Fehlerbehebung

### `composition definition is not loaded: dix/cli/typer`

Ein alter oder unvollstaendiger Launcher hat `dix/roba` geladen, ohne zuvor `dix/state` und
`dix/cli` zu laden. `dix-roba` aus der oben gezeigten committeten DIX-Spec neu bauen und
installieren. Seine Modulliste nicht von Hand kuerzen.

### Manager-Socket fehlt

Ein typischer Fehler nennt einen fehlenden Socket unter
`$DIX_ROBA_RUNTIME_ROOT/daemons/default/contexts/dix.control/sockets/` oder im Default-Baum
`~/.roba/runtime/...`. Sicherstellen, dass `managed start` erfolgreich war, und danach
`skaldos-sway` exakt einmal erzeugen. Nach einem Daemon-Neustart existieren die alten Sockets und
Contexts nicht mehr; beide Schritte wiederholen.

### Ein Socketpfad enthaelt das falsche `~` oder wird relativ

Shells expandieren `~` nicht innerhalb beliebiger gequoteter Variablen oder erzeugter Strings.
Absolute Pfade in `DIX_ROBA_RUNTIME_ROOT` und `DIX_ROBA_LOGS_ROOT` verwenden und sicherstellen,
dass der Prozess fuer Terminal, Wofi oder Sway-Binding beide Werte bereitstellt. Eine partielle
Custom-Root-Konfiguration richtet verschiedene Prozesse auf verschiedene Daemons und wird nicht
unterstuetzt.

### ROBA laeuft, aber `skaldos-sway` fehlt

Daemon-Status allein reicht nicht. Den Befehl
`control create_context --context_id skaldos-sway` ausfuehren. Meldet er einen bereits vorhandenen
Context, keinen zweiten erzeugen; Manager-Socket-Pfad pruefen und sicherstellen, dass jeder Befehl
dieselbe Daemon-Konfiguration verwendet.

### Navigation meldet eine fehlende oder ungueltige Projektion

Die drei `SKALDOS_SWAY_*_FILE`-Werte im aufrufenden Prozess pruefen. `navigation-target` muss exakt
`basic\n` oder `group\n` sein; `active-members` muss eine newline-terminierte, space-separierte
Zeile positiver IDs sein. Beide durch `skaldos-sway-json select <gruppe>` neu erzeugen. Korrupte
Dateien nicht durch Raten eines anderen Formats reparieren.

### Sway oder i3ipc kann keine Verbindung herstellen

Folgendes aus derselben Umgebung pruefen:

```sh
printf '%s\n' "$SWAYSOCK"
swaymsg -t get_tree >/dev/null
"$DIX_ROOT/.venv/bin/python" -c 'import i3ipc; print(i3ipc.__version__)'
```

Scheitert der Import, die explizite Requirements-Installation wiederholen. Scheitert `swaymsg`,
den Befehl in der richtigen Sway-Session ausfuehren; das Modul erzeugt oder entdeckt keinen
Display-Server.

## Bekannte Alpha-Grenzen

- Kein Daemon oder Context wird automatisch gestartet.
- Kein Package Manager und keine automatische externe Modul-Discovery existieren.
- Custom-ROBA-Roots sind Prozess-Environment-Defaults; jeder unabhaengig gestartete Consumer muss
  dieselben Werte erben.
- Gruppenmitgliedschaft verwendet Sway-Runtime-Container-IDs und keine persistenten
  Anwendungsidentitaeten.
- In diesem Slice gibt es keinen Befehl zum Loeschen einer Gruppe.
- Wofi und Sway-Konfiguration bleiben optionale Integrationen in Nutzer-Ownership.
- Tests nutzen Fake-i3ipc- und Fake-Wofi-Grenzen; nach der Installation einen echten
  Desktop-Smoke-Test ausfuehren.
- DIX und dieses Modul fuehren vertrauenswuerdiges Python in-process aus und bieten keine
  Security-Sandbox.

## Visueller Nachweis

Ein echter Screenshot oder eine Aufnahme wird erst nach einem menschlichen Lauf der
veroeffentlichten Anleitung ergaenzt. Synthetisches Material wird nicht als Ausfuehrungsbeleg
ausgegeben.

## Entwicklungspruefung

Vom Repository-Root nach Vorbereitung von DIX und Installation von `sway/requirements.txt`:

```sh
DIX_REPOSITORY="$DIX_ROOT" "$DIX_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
python tests/verify_public_docs.py
```

## Lizenz

Apache License 2.0. Siehe [`../LICENSE`](../LICENSE).
