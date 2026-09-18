# Skaldos DIX-Module

Externe, explizit komponierte Module fuer [DIX](https://github.com/skaldos/dix).

Der Branch `sway` ist ein fokussierter Architekturbranch. Er liefert aktuell nur zwei getrennt
ladbare Sway-Module:

```text
sway/core  -> policyfreies Sway-IPC
sway/nav   -> Navigationsalgorithmen, Runtime-Binding, Applications und Delivery
```

Die frueheren Group-, Theme-, ROBA-, Wofi- und Profile-Experimente sind bewusst nicht enthalten.
Ihre Historie bleibt auf `main` und kann spaeter als getrennte Module zurueckkehren, ohne den alten
Monolithen wiederherzustellen.

Einstieg: [deutsche Sway-Anleitung](sway/README.de.md) oder
[englische Sway-Anleitung](sway/README.md).

## Lizenz

Apache-2.0. Siehe [LICENSE](LICENSE).
