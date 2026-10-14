# Skaldos DIX-Module

Externe, explizit komponierte Module fuer [DIX](https://github.com/skaldos/dix).

Der `sway`-Baum liefert aktuell drei getrennt ladbare Sway-Module:

```text
sway/core  -> policyfreies Sway-IPC
sway/nav   -> Navigationsalgorithmen, Runtime-Binding, Applications und Delivery
sway/theme -> modellierte Theme-Strands, Knot-Application und CLI-Delivery
```

Die frueheren Group-, ROBA-, Wofi- und Profile-Experimente sind bewusst nicht enthalten. Ihre
Historie kann spaeter als getrennte Module zurueckkehren, ohne den alten Monolithen
wiederherzustellen.

Einstieg: [deutsche Sway-Anleitung](sway/README.de.md) oder
[englische Sway-Anleitung](sway/README.md).

Die getrennte [VisiData-Loom-Workbench](visidata/README.de.md) (auch
[auf Englisch](visidata/README.md)) ist ein providerneutraler V0-Client mit direkt in-process
gebundener `dix/roba/loom`-Application; sie gehoert nicht zu den Sway-Modulen.

Das [DIX Cockpit](cockpit/README.de.md) (auch [auf Englisch](cockpit/README.md)) liefert einen isolierten privilegierten tmux-/Zsh-Arbeitsraum mit eigener Cockpit-ROBA-Runtime.

## Lizenz

Apache-2.0. Siehe [LICENSE](LICENSE).
