# Skaldos DIX modules

External, explicitly composed modules for [DIX](https://github.com/skaldos/dix).

The `sway` tree currently ships three independently loadable Sway modules:

```text
sway/core  -> policy-free Sway IPC
sway/nav   -> navigation algorithms, runtime binding, applications and delivery
sway/theme -> modeled Theme strands, a Knot-driven application and CLI delivery
```

It deliberately does not ship the earlier group, ROBA, Wofi or profile experiments. Their history
may return later as separate modules instead of rebuilding one monolith.

Start with the [English Sway guide](sway/README.md) or the
[German Sway guide](sway/README.de.md).

The separate [VisiData Loom workbench](visidata/README.md) (also
[in German](visidata/README.de.md)) is a provider-neutral V0 client delivered with a direct
in-process `dix/roba/loom` application; it is not part of the Sway modules.

The [DIX Cockpit](cockpit/README.md) (also [in German](cockpit/README.de.md)) adds an isolated
tmux workspace and explicit multi-daemon catalog around that unchanged Loom workbench.

## License

Apache-2.0. See [LICENSE](LICENSE).
