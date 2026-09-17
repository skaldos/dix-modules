# Skaldos DIX Modules

Von Skaldos gepflegte externe Source-Module fuer
[DIX](https://github.com/skaldos/dix).

[English](README.md) · [DIX](https://github.com/skaldos/dix) ·
[ROBA](https://github.com/skaldos/roba) ·
[Anleitung fuer `skaldos/sway`](sway/README.de.md)

> **Public Alpha:** Die Module sind getestet und nutzbar, ihre Source-Vertraege und Einrichtung
> koennen sich aber noch aendern. Fuer reproduzierbare Nutzung sollten Repository-Staende gepinnt
> werden.

Die Dokumentation ist auf Englisch und Deutsch verfuegbar. Ausgelieferte Befehlsnamen, Prompts und
maschinennahe Fehlermeldungen sind englisch.

## Was dieses Repository ist

Jeder Modulordner auf oberster Ebene ist eine direkt ladbare DIX-Modulwurzel. Wird dieses
Repository als `dix/modules/skaldos` geklont, wird der Ordner `sway/` explizit mit der Modul-ID
`skaldos/sway` geladen:

```text
workspace/
├── roba/
└── dix/
    └── modules/
        ├── dix/             # durch DIX gelieferte Module
        └── skaldos/         # dieses Repository
            └── sway/        # externes Modul skaldos/sway
```

Dieses Repository ist eine Source-Modulbibliothek. Es ist bewusst **keine** Python-Distribution,
kein DIX-Package-Manager, keine Modulregistry, kein Git-Submodule und kein automatischer Installer.
Jedes Modul behaelt seine eigenen Dependencies, Tests, optionalen Integrationen und
Release-Entscheidungen.

## Verfuegbare Module

### `skaldos/sway`

Ein realer externer DIX-Consumer fuer topology-aware Sway-Fenstergruppennavigation:

```text
Sway IPC
+ ROBA coordination state
+ DIX compositions/applications
+ fixed low-latency keybindings
+= topology-aware window-group navigation
```

Das Modul liefert:

- explizites Gruppenmanagement ueber DIX und ROBA;
- private dateiverantwortete Fenstermitgliedschaft;
- schmale atomare Route- und Active-Member-Projektionen fuer Navigation;
- native richtungsbasierte und topology-aware Gruppennavigation;
- vollstaendige persistente Sway-Themes mit getrennt komponierbaren Datei-, IPC- und
  Active-Marker-Faehigkeiten;
- einen dependency-armen direkten Navigationseinstieg;
- optionale Wofi-Adapter und ein Sway-Konfigurationsfragment.

Lies die vollstaendige [deutsche Einrichtung](sway/README.de.md) oder die
[englische Einrichtung](sway/README.md).

## Source-Assembly

Das vollstaendige oeffentliche Beispiel nutzt drei benachbarte Source-Repositories:

```sh
mkdir -p skaldos-sway-showcase
cd skaldos-sway-showcase
git clone https://github.com/skaldos/roba.git roba
git clone https://github.com/skaldos/dix.git dix

cd dix
uv sync --frozen --extra dev --extra cli --extra state --extra roba
cd ..

git clone https://github.com/skaldos/dix-modules.git dix/modules/skaldos
```

DIX wird vorbereitet, bevor der externe Checkout unter `dix/modules` abgelegt wird. Diese
Reihenfolge begrenzt eine lokal gebaute DIX-Distribution auf die Module ihres committeten Sources;
bereits unter `modules/` vorhandene Verzeichnisse sind Build-Inputs. Der externe Checkout wird
danach aus seinem Sourcepfad konsumiert und nicht als Teil von DIX neu gebaut.

DIX entdeckt diesen Checkout nicht automatisch. Die Sway-Application und ihre Launcher uebergeben
Source-Pfad und Modul-ID explizit.

## Ownership-Grenzen

- **DIX** baut lokale Composition- und Application-Graphen. DIX liefert weder Sway noch `i3ipc`.
- **ROBA** liefert ephemeren Koordinationsstate. ROBA persistiert Gruppen nicht ueber einen
  Daemon-Neustart und ist kein Credential-Store.
- **`skaldos/sway`** verantwortet Sway-IPC, Gruppenverhalten, Projektionen, direkte Navigation,
  Dependencies und Desktop-Integrationen.
- **Der Nutzer** verantwortet Clone-Pfade, Prozessstart, lokale State-Pfade, Keybindings und die
  Betriebssystem-Zugriffsgrenze.

Als DIX-Modul geladener Python-Code laeuft im Prozess des Aufrufers. Weder dieses Repository noch
DIX ist eine Security-Sandbox.

## Entwicklung

Nutze einen expliziten DIX-Checkout und installiere die modulverantwortete Dependency in dessen
Umgebung:

```sh
DIX_ROOT=/absoluter/pfad/zu/dix
MODULES_ROOT=/absoluter/pfad/zu/dix-modules

cd "$DIX_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba
uv pip install --python .venv/bin/python -r "$MODULES_ROOT/sway/requirements.txt"

cd "$MODULES_ROOT"
DIX_REPOSITORY="$DIX_ROOT" "$DIX_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
```

Die Testsuite nutzt deterministische Fakes an den Sway-/i3ipc- und Wofi-Grenzen. Ein erfolgreicher
Testlauf behauptet keinen Test in einer realen Desktop-Session.

## Lizenz

Apache License 2.0. Siehe [`LICENSE`](LICENSE).
