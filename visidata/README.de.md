# Skaldos VisiData-Workbench (V0)

Ein kleiner interaktiver JSON-Editor fuer **einen vorhandenen** ROBA-Context-
Key. Keine ROBA-Admin-UI, kein persistenter Profil-Editor und kein generischer
Command-Runner. Das technische [`roba-key.toml`](templates/roba-key.toml)
benennt bekannte Get-/Set-Operationen; das getrennte
[`profile.toml`](templates/profile.toml) benennt das editierbare Feld. Erst die
Laufzeitbindung waehlt Context-Socket und Key. VisiData bearbeitet eine lokale
Kopie; nur ausdrueckliches **Apply** schreibt.

## Installation

Voraussetzungen: Python 3.12, `uv`, installiertes `dix-roba-cli`, vorhandener
ROBA-Context mit **Read+Write-Capability-Socket**. `chafa` ist fuer die
PNG-Anzeige optional. Der Installer baut eine eigene VisiData-3.4-Venv samt
schmalem Launcher und veraendert weder DIX/ROBA noch deren Runtime:

```sh
# Bei angepasstem DIX_BIN vorher die eigene zentrale Env laden:
# . "$HOME/.dix/env"
./visidata/integrations/install
```

`DIX_BIN` ist standardmaessig `~/.local/bin`;
`SKALDOS_WORKBENCH_VENV` ist standardmaessig
`${XDG_DATA_HOME:-~/.local/share}/skaldos/visidata-venv`. Der Launcher zeigt
auf diesen Checkout; nach dessen Verschiebung erneut installieren.

`dix-roba-cli` wie in der DIX-ROBA-Anleitung bauen/installieren. Im vorhandenen
Context einen Capability-Socket mit nativem `read` **und** `write` fuer den
Context (oder die exakt adressierte Instanz) erzeugen und dessen Pfad nutzen.
**Keinen** Owner-Token an die Workbench geben:

**Capability-Scope ist nicht Key-Scope.** Ein Socket mit `read`/`write` auf
`context` kann auch andere Keys in diesem Context bedienen; nur die
Workbench selbst bindet sich an den gewaehlten Key. Socketpfad schuetzen
und fuer Experimente besser einen eigenen Test-Context nutzen.

```sh
skaldos-workbench \
  --dix-roba-cli "$HOME/.local/bin/dix-roba-cli" \
  --locator unix:/absoluter/context/sockets/rw.sock \
  --key profile \
  --logo dix
```

Mit `--logo roba` wird das andere aktuelle PNG gewaehlt. Beide stammen aus
den vom Nutzer benannten `/cwd/pocs/gimp-mcp`-Assets:

| Asset | SHA-256 |
| --- | --- |
| `assets/dix.png` | `3f2c47cdbf876a51453344bf2e6693180116a684b4b88888591c42233793ad87` |
| `assets/roba.png` | `921757a4abb2e0e19ef647a2129b3396a29a82c436d4ee5d0eb333e0339c22b8` |

Das PNG erscheint beim Start und mit **B** erneut aus VisiData. Der konkrete
Aufruf lautet `chafa --fill block -c full --scale 0.5 <PNG>`. Auf schmalen
Terminals oder ohne `chafa` erscheint stattdessen ein Textlabel; die
Bearbeitung bleibt moeglich. Der Installer generiert/laedt keine Bilder.

## Bedienung

| Taste | Wirkung |
| --- | --- |
| Enter | Objekt/Liste oeffnen |
| e | Vorhandenen Skalar als JSON editieren (`"Text"`, `42`, `true`, `null`) |
| a | **Ganzen** lokalen Key-Wert ueber `dix-roba-cli data set` anwenden |
| B | Gewaehltes PNG erneut zeigen |
| q | In VisiData zurueck/beenden |

Nach lokaler Aenderung steht `*draft*` im Sheet-Namen. Ein Apply-Fehler
laesst den Entwurf stehen. V0 kann keine Keys/Listeneintraege einfuegen oder
loeschen, Container nicht inline ersetzen, und kennt weder CAS noch
Mehrwriter-Erkennung. **Apply ersetzt den ganzen Key** und kann damit eine
parallele Aenderung an diesem Key ueberschreiben; Nachbar-Keys bleiben
unveraendert. Kein automatischer Readback, kein Write der Template-Datei,
keine ROBA-Persistenz-/Restart-Zusage. Backendfehler werden ohne Ausgabe des
uebergebenen JSON oder von Credentials zusammengefasst.

Tests vom Repo-Root: `uv run --no-project --with visidata==3.4 --with
pytest==9.1.1 --python 3.12 python -m pytest -q
tests/test_visidata_workbench_*.py`. Menschliche Sichtabnahme braucht ein
echtes Terminal.
