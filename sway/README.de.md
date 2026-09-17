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
| Theme-Katalog | Vollstaendige nutzereigene TOML-Definitionen im konfigurierten Theme-Ordner. |
| Aktive Theme-Projektion | Zuletzt durch diese Application erfolgreich angewendete ID; kein Live-Sway-State. |
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
export DIX_SOURCE_ROOT=$SKALDOS_WORKSPACE/dix
```

Den externen Checkout nicht vor dem initialen DIX-Sync unter `dix/modules` ablegen. Dort bereits
vorhandene Verzeichnisse sind Inputs einer lokal gebauten DIX-Distribution. Wird zuerst der
committete DIX-Source vorbereitet, bleibt diese Distribution auf DIX-eigene Module begrenzt; der
externe Checkout kommt danach als Source-Consumer hinzu.

## 2. DIX-Umgebung vorbereiten

DIX verweist in dieser Struktur bereits auf den benachbarten Source `../roba`. Die deklarierten
Extras synchronisieren und danach die Sway-eigenen Requirements in dieselbe Umgebung installieren:

```sh
cd "$DIX_SOURCE_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba

git clone https://github.com/skaldos/dix-modules.git "$DIX_SOURCE_ROOT/modules/skaldos"
export SWAY_ROOT=$DIX_SOURCE_ROOT/modules/skaldos/sway

uv pip install --python "$DIX_SOURCE_ROOT/.venv/bin/python" -r "$SWAY_ROOT/requirements.txt"
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

## 3. Eine zentrale DIX-Umgebung anlegen

Das kommentierte XDG-orientierte Template einmal installieren. Nur diese Datei wird von den
lokalen Befehlen geladen:

```sh
mkdir -p "$HOME/.dix"
cp "$SWAY_ROOT/integrations/env" "$HOME/.dix/env"
${EDITOR:-vi} "$HOME/.dix/env"
```

Die Defaults verwenden passend `XDG_RUNTIME_DIR`, `XDG_STATE_HOME` und `XDG_DATA_HOME`. Fuer einen
eigenen Baum wie `~/.dix` werden nur hier Werte ueberschrieben, nicht in Sway.
`SKALDOS_SWAY_GROUP_STATE_FILE`, `SKALDOS_SWAY_ACTIVE_MEMBERS_FILE`,
`SKALDOS_SWAY_NAVIGATION_TARGET_FILE`, `SKALDOS_SWAY_THEME_DIR` und
`SKALDOS_SWAY_ACTIVE_THEME_FILE` bleiben getrennte Grenzen. Theme-TOMLs sind persistente
Nutzerkonfiguration; `active-theme` ist nur eine ersetzbare Projektion der zuletzt durch diese
Application erfolgreich angewendeten ID.

`groups.json` ist lokaler Nutzerzustand. Die Projektionsdateien sind ersetzbare Ausgaben und
duerfen nicht in ungueltige Werte editiert werden.

## 4. Lokale Launcher und Befehle bauen und installieren

Der Management-Einstieg benoetigt einen laufenden ROBA-Daemon, die DIX-Control-Registry und einen
verwalteten Context. Der Integrationsinstaller baut die committete Typer-Application, kopiert beide
Sway-Python-Launcher und installiert die kleinen Befehle unter `DIX_BIN`:

```sh
"$SWAY_ROOT/integrations/install"
export PATH=$HOME/.local/bin:$PATH
dix-roba --help
skaldos-sway --help
```

Die resultierenden Befehle `dix-roba`, das vollstaendige Typer-basierte `skaldos-sway`, das direkte
`skaldos-sway-json`, das latenzarme `skaldos-sway-nav` und die Wofi-Helfer laden alle
`~/.dix/env`. Ihre Python-Launcher liegen gemeinsam unter `DIX_LAUNCHERS`.

Der Installer kopiert ausserdem die vollstaendigen Beispiele `dix.toml` und `roba.toml` nach
`SKALDOS_SWAY_THEME_DIR`, falls sie dort noch fehlen. Ein erneuter Lauf ueberschreibt keines der
beiden Ziele.

## 5. ROBA konfigurieren, starten und `skaldos-sway` erzeugen

Ohne Overrides behaelt DIX selbst die belegte Daemon-ID `default`, den Runtime-Root
`~/.roba/runtime` und den Log-Root `~/.roba/logs`. Das installierte Environment-Template gibt
stattdessen jedem lokalen Befehl XDG-orientierte Werte fuer `DIX_ROBA_RUNTIME_ROOT` und
`DIX_ROBA_LOGS_ROOT`:

```sh
dix-roba managed start
dix-roba control create_context \
  --context_id skaldos-sway
dix-roba daemon status
```

`managed start` startet ROBA und bootstrapt den DIX-Control-Context. `create_context` erzeugt danach
den Modul-Context und dessen Manager-Socket. Diese Befehle geben capability-tragende Ergebnisdaten
aus; Tokens gehoeren nicht in Dokumentation, Logs oder Tickets.

Fuer beliebige absolute nutzereigene Pfade werden die beiden Werte in `~/.dix/env` gesetzt:

```sh
export DIX_ROBA_RUNTIME_ROOT=/absoluter/pfad/zur/roba-runtime
export DIX_ROBA_LOGS_ROOT=/absoluter/pfad/zu/roba-logs
```

Jeder installierte Befehl liest dieselbe Datei. Benannte Typer-Parameter wie `--runtime_root` und
`--logs_root` ueberschreiben sie weiterhin fuer einen Aufruf. Kein nicht expandiertes literales
`~` in Custom-Pfaden verwenden.

`create_context` nicht wiederholt gegen einen bereits existierenden Context ausfuehren. Ein
Duplikat ist ein sichtbarer Fehler und kein Attach-Vorgang.

## 6. Die transparenten Wrapper pruefen

Der Installer hat die Wrapper bereits unter `DIX_BIN` abgelegt. Sie enthalten nur diese Grenze:

```sh
cat "$HOME/.local/bin/skaldos-sway-nav"
cat "$HOME/.local/bin/skaldos-sway-json"
```

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

## 8. Vollstaendige Themes verwalten

Die vollstaendige Typer-Application exponiert den getrennt komponierten Theme-Katalog und die
Sway-IPC-Funktionen:

```sh
skaldos-sway theme list
skaldos-sway theme show --theme dix
skaldos-sway theme apply --theme dix
skaldos-sway theme current
skaldos-sway theme create --theme personal
```

Alle Parameter sind benannte Optionen. Fuer einen Aufruf koennen der persistente Katalog und die
aktive Projektion mit `--theme_dir /absoluter/pfad/themes` und
`--active_theme_file /absoluter/pfad/state/active-theme` ueberschrieben werden. Die zentralen
Defaults bleiben `SKALDOS_SWAY_THEME_DIR` und `SKALDOS_SWAY_ACTIVE_THEME_FILE` in `~/.dix/env`.

Jedes Theme ist vollstaendig: Alle wirksamen Sway-Client-Farbklassen sind Pflicht. Ein Theme kann
den Output-Hintergrund auslassen, eine Vollfarbe nutzen oder ein Bild fuer `output *` setzen:

```toml
[background]
type = "image"
file = "wallpapers/example.png"
mode = "fill"
fallback_color = "#10080E"
```

Relative Bilder werden gegen die Theme-Datei aufgeloest. `theme current` meldet nur die zuletzt
durch diese Application erfolgreich angewendete ID. Der Befehl inspiziert Sway nicht live; ein
nach einem Sway-Neustart vorhandener Marker beweist kein erneutes Apply in der neuen Session.

## 9. Navigation direkt testen

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

## 10. Optionale Wofi-Befehle

Der Installer stellt drei direkte Befehle bereit:

```sh
skaldos-sway-wofi-select
skaldos-sway-wofi-add
skaldos-sway-wofi-remove
```

Ihre Source-Adapter bleiben unter `integrations/wofi/select`, `integrations/wofi/add` und
`integrations/wofi/remove`.

Die Menues fuer vorhandene Eintraege starten Wofi mit `--no-custom-entry`. Enter auf der initial
hervorgehobenen Zeile uebernimmt diese deshalb ohne vorherige Cursorbewegung. Nur der getrennte
Dialog fuer einen neuen Gruppennamen erlaubt freie Texteingabe.

Die Aktionszeilen lauten `[No active group]` und `[+ New group]`. Add und Remove verwenden die
Prompts `Add window to group` und `Remove window from group`; die freie Eingabe eines Gruppennamens
verwendet `New group name`.

`SKALDOS_SWAY_MANAGEMENT`, `SKALDOS_SWAY_WOFI` oder `SKALDOS_SWAY_WOFI_NAME` nur ueberschreiben,
wenn der Ersatzbefehl bewusst selbst verantwortet wird. Diese Variablen sind Shell-Command-
Grenzen und keine DIX-API.

## 11. Sway-Bindings hinzufuegen

Das vollstaendige gepflegte Fragment liegt unter
[`integrations/sway/config`](integrations/sway/config). Es in die Sway-Konfiguration kopieren und
`/home/YOU` durch das reale absolute Home-Verzeichnis ersetzen:

```text
set $skaldos_home /home/YOU
set $skaldos_bin $skaldos_home/.local/bin

bindsym $mod+h exec --no-startup-id $skaldos_bin/skaldos-sway-nav left
bindsym $mod+j exec --no-startup-id $skaldos_bin/skaldos-sway-nav down
bindsym $mod+k exec --no-startup-id $skaldos_bin/skaldos-sway-nav up
bindsym $mod+l exec --no-startup-id $skaldos_bin/skaldos-sway-nav right

bindsym $mod+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-select
bindsym $mod+Shift+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-add
bindsym $mod+Ctrl+g exec --no-startup-id $skaldos_bin/skaldos-sway-wofi-remove
```

Sway erhaelt keine DIX-spezifische Umgebung. Jeder Befehl laedt die aktuellen Werte aus
`~/.dix/env`; eine Aenderung dort gilt beim naechsten Aufruf ohne Sway-Reload.

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
"$DIX_SOURCE_ROOT/.venv/bin/python" -c 'import i3ipc; print(i3ipc.__version__)'
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
DIX_REPOSITORY="$DIX_SOURCE_ROOT" "$DIX_SOURCE_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_SOURCE_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
python tests/verify_public_docs.py
```

## Lizenz

Apache License 2.0. Siehe [`../LICENSE`](../LICENSE).
