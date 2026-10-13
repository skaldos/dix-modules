# Direkte VisiData-Loom-Workbench (V0)

Dieses Modul ist ein providerneutraler VisiData-Client fuer den geschlossenen Loom-Vertrag:

```python
execute(value, object_id=None)
# -> [{"object_id": str, "description": str, "value": object}, ...]
```

Die gelieferte DIX-Application bindet den generischen Workbench direkt und in-process an
`dix/roba/loom`. Sie ruft weder `dix-roba-cli` auf noch waehlt sie Provider, Commands oder Imports
aus editierten Daten. `dix-roba-workbench` verlangt immer einen expliziten JSON-Seed.

## Installation

Voraussetzungen sind Python 3.12, `uv`, eine DIX-Venv mit ROBA-Extra sowie aktuelle Checkouts von
DIX und diesen `dix-modules`. Die zentrale Umgebung liegt standardmaessig in `~/.dix/env` und muss
definieren:

```sh
DIX_SOURCE_ROOT=...  # DIX-Source-Checkout
DIX_VENV=...         # DIX-Venv mit ROBA-Unterstuetzung
DIX_LAUNCHERS=...
DIX_BIN=...
```

VisiData 3.4 in diese DIX-Venv installieren und den normalen `python_cli`-Launcher bauen:

```sh
. "$HOME/.dix/env"
./visidata/integrations/install
```

Der Installer erzeugt nur `dix-roba-workbench` und entfernt einen vorhandenen alten Wrapper
`$DIX_BIN/skaldos-workbench`. Unbekannte Nutzerdateien oder alte Venvs loescht er nicht. Der
DIX-Launcher laedt derzeit auch `dix/cli`, weil das vollstaendige Modul `dix/roba` selbst eine
CLI-Application deklariert; der Providerpfad des Workbench ruft diese CLI niemals auf.

## Seed und Start

Eine Daemon-Konfiguration ist der kleinste sinnvolle ROBA-Loom-Seed. Fuer Experimente isolierte
Pfade verwenden:

```json
{
  "daemon_id": "workbench-test",
  "runtime_root": "/tmp/workbench-test/runtime",
  "logs_root": "/tmp/workbench-test/logs",
  "timeout": 5.0
}
```

```sh
dix-roba-workbench --seed ./seed.json --logo dix
# alternativ: --logo roba
# nur fuer lokale Drucktests: --no-confirm
```

Ungueltiges oder unlesbares JSON scheitert vor VisiData und vor jedem Providercall. Beide
gelieferten PNGs behalten ihre dokumentierten SHA-256-Werte:

| Asset | SHA-256 |
| --- | --- |
| `assets/dix.png` | `3f2c47cdbf876a51453344bf2e6693180116a684b4b88888591c42233793ad87` |
| `assets/roba.png` | `921757a4abb2e0e19ef647a2129b3396a29a82c436d4ee5d0eb333e0339c22b8` |

Branding nutzt `chafa --fill block -c full --scale 0.5`. Fehlendes Chafa, umgeleitete Ein-/Ausgabe
oder ein kleines Terminal blockieren den Workbench nie.

## Tasten und Wirkungen

Reference-Sheet:

| Taste | Wirkung |
| --- | --- |
| Enter | Vollstaendige Reference als abgeloesten lokalen Draft inspizieren; nie ausfuehren |
| Space | `object_id` und Wert anzeigen, bestaetigen lassen, dann exakt einmal ausfuehren |
| B | Gewaehltes Logo erneut anzeigen |
| q | In VisiData zurueck/beenden |

Draft-Sheet:

| Taste | Wirkung |
| --- | --- |
| Enter | In Mapping/Liste drillen; nie ausfuehren |
| e | Gewaehlten JSON-kompatiblen Skalar lokal ersetzen |
| r | Vollstaendigen JSON-kompatiblen Teilbaum lokal ersetzen |
| Space | Vollstaendigen Draft anzeigen, bestaetigen und exakt einmal ausfuehren |
| q | Zum vorherigen Sheet zurueckkehren |

**Jede Reference kann eine externe Wirkung darstellen.** Der generische Client klassifiziert Namen
wie `read`, `write`, `start` oder `delete` bewusst nicht. Enter, Edit, Sheetnavigation und Ende
bleiben lokal; nach der initialen Seed-Aufloesung ruft nur **Space** den Provider. Im
Defaultmodus wird immer bestaetigt. Die explizite Option `--no-confirm` ueberspringt diese Nachfrage
und ist nur fuer kontrollierte lokale Drucktests gedacht. Cancel ruft nichts auf.
Providerexceptions bleiben sichtbar und erhalten den Draft. Ein leeres Ergebnis ist erfolgreich
und oeffnet ein leeres Reference-Sheet. Jedes Reference-Sheet besitzt die vollstaendigen Werte,
die es angezeigt hat; ein altes Sheet loest seine Zeilen daher nie gegen ein neueres
Providerresultat auf. History ist nur Navigation, niemals Undo oder Rollback externer Wirkungen.
Auf diesen beiden Workbench-Sheets ersetzt Space bewusst Visidatas normale Zeilenauswahl; dieser
Client konsumiert keine Mehrfachauswahl. Eine terminalspezifische Tastenabbildung ist nicht noetig.

Das lokale interaktive Sheet zeigt absichtlich vollstaendige Werte, einschliesslich von ROBA
gelieferter Tokens und Socket-Capabilities. Nur in einem vertrauenswuerdigen Terminal verwenden;
Screenshots, Scrollback und Aufzeichnungen schuetzen. V0 besitzt keine automatische Redaction,
Clipboard-/Export-Policy, Credential-Recovery, Session-Persistenz, CAS,
Mehrwriter-Konfliktbehandlung oder Rollback. Native Nicht-JSON-Werte sind inspizierbar, koennen
aber nicht verlustbehaftet zurueckgeschrieben werden.

## Tests

Vom Repository-Root mit verfuegbarem gepinnten ROBA-Source:

```sh
uv run --no-project --with /cwd/repos/roba --with visidata==3.4 \
  --with pytest==9.1.1 --python 3.12 \
  python -m pytest -q tests/test_visidata_*.py
```

Der reale Test nutzt nur einen temporaeren Daemon und temporaeren State. Die interaktive
Sichtabnahme benoetigt weiterhin ein echtes Terminal.
