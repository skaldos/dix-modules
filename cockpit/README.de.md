# DIX Cockpit

DIX Cockpit ist ein isolierter tmux-Arbeitsraum fuer mehrere explizite ROBA-Daemon-Wurzeln. Jedes
Connection-Window verwendet die vorhandene providerneutrale VisiData-Loom-Workbench. Das Cockpit
orchestriert nur den Arbeitsraum: Start oder Stop des Cockpits startet beziehungsweise stoppt
niemals einen ROBA-Daemon.

## Voraussetzungen und Installation

- DIX mit `dix/state`, `dix/cli`, `dix/norn` und `dix/roba`;
- dieses Repository mit den benachbarten Modulwurzeln `visidata` und `cockpit`;
- `uv`, Python 3.12+, tmux und das zentrale DIX-Environment;
- VisiData 3.4 (wird vom Installer in `DIX_VENV` installiert);
- optional `chafa`, `wl-copy`/`wl-paste` oder `xclip`.

```sh
export DIX_ENV="$HOME/.dix/env"       # optional; das ist der Default
./cockpit/integrations/install
```

Der Installer baut drei normale DIX-Launcher, installiert `dix-cockpit` samt internen
Window-Helfern in `DIX_BIN` und kopiert die Cockpit-eigene tmux-Config unter
`DIX_LAUNCHERS/cockpit`. Der Default-Katalog wird nur angelegt, wenn er noch nicht existiert. Das
zentrale DIX-Env und vorhandene Katalogdateien bleiben unveraendert; eine Host-tmux-Config wird
nicht geladen.

Optionale Overrides:

```sh
export DIX_COCKPIT_CATALOG="$HOME/.config/skaldos/cockpit/daemons.toml"
export DIX_COCKPIT_RUNTIME_ROOT="${XDG_RUNTIME_DIR:-/tmp}/dix-cockpit"
export DIX_COCKPIT_TMUX_CONFIG="$DIX_LAUNCHERS/cockpit/tmux.conf"
export SKALDOS_VISIDATA_ROOT="$HOME/.dix/src/dix-modules/visidata"
```

`DIX_COCKPIT_RUNTIME_ROOT` sollte kurz bleiben. Cockpit prueft das enge Plattformlimit fuer
Unix-Socketpfade vor jedem tmux-Aufruf.

## Expliziter Daemon-Katalog

```toml
[daemons.default]
daemon_id = "default"
runtime_root = "~/.roba/runtime"
logs_root = "~/.roba/logs"
timeout = 5.0

[daemons.lab]
daemon_id = "lab"
runtime_root = "/run/user/1000/roba-lab"
logs_root = "~/.local/state/roba-lab/logs"
```

Der Tabellenname ist die stabile lokale Katalog-/Window-Identitaet; `daemon_id` ist die
Provideridentitaet. Relative Wurzeln beziehen sich auf das Katalogverzeichnis, `~` wird
aufgeloest. Unbekannte Felder, Duplikate, leere Werte und ungueltige Timeouts scheitern sichtbar.
Der Katalog ist keine Discovery und darf keine Tokens enthalten.

## Commands und Lifecycle

```sh
dix-cockpit start  [--session NAME] [--catalog PATH] [--logo dix|roba]
dix-cockpit attach [--session NAME]
dix-cockpit status [--session NAME]
dix-cockpit stop   [--session NAME]
```

Session und Logo verwenden standardmaessig `dix`. `start` erzeugt oder fokussiert die eigene
Cockpit-tmux-Session und attached. `attach` und `status` erzeugen nichts. `stop` entfernt nur die
benannte Cockpit-Session und raeumt den leeren isolierten tmux-Server auf; Katalog-Daemons bleiben
unberuehrt.

Das Control-Window zeigt auch gestoppte und fehlerhafte Ziele. Reload verwendet den normalen
VisiData-Reload. Enter oeffnet oder fokussiert ohne Loom-Wirkung genau ein stabiles
Connection-Window. Dort gilt die unveraenderte Loom-Workbench-Bedienung:

- **Enter**: nur inspizieren/oeffnen/drillen;
- **Space**: die gewaehlte Loom-Reference bestaetigt ausfuehren;
- `e` / `r`: Skalar editieren beziehungsweise JSON-kompatiblen Draft-Teilbaum ersetzen;
- `B`: das ausgewaehlte Branding anzeigen, sofern verfuegbar.

Ein gestopptes Ziel beginnt mit der Basis-Connection und bietet dadurch ein explizites Loom-
`start`. Ein laufendes Ziel wird in-process ueber DIX Control aufgeloest. Kaputte Control-
Credentials bleiben ein sichtbarer Fehler und werden nicht durch erfundene oder schwaechere
Credentials ersetzt.

## Isoliertes tmux und Clipboard

Jeder tmux-Aufruf verwendet denselben dedizierten `-S`-Socket. Nur die Servererzeugung laedt die
Cockpit-Config. Hostserver, Hostconfig und Plugins bleiben unberuehrt. Cockpit liefert `C-a`
(sowie nested `C-b`), vi-Copy-Mode, h/j/k/l-Pane-Navigation, C-h/C-l-Window-Navigation,
H/J/K/L-Resize, `|`/`-`-Splits, Escape-Copy-Mode und eigene Header-/Statusflaechen.

Copy/Paste verwendet zuerst Wayland, danach Xclip und zuletzt den isolierten tmux-Buffer. Die
Helfer reichen Bytes ueber stdin/stdout durch und interpolieren Clipboard-Inhalt nie als
Shellcommand. Der Fallback wird im Terminal sichtbar gemeldet.

## Secret-Grenze

Die lokale Connection-Workbench zeigt fuer diesen Drucktest bewusst vollstaendige materialisierte
Werte einschliesslich Tokens. Diese Werte bleiben im Prozess. Tokens werden niemals in argv,
tmux-Namen/-Optionen, Header/Status, Logs, Dokumentation oder Katalogdateien kopiert. Eine reale
Terminal-/Sichtabnahme bleibt von automatischen Tests getrennt.
