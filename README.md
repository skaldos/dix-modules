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

## License

Apache-2.0. See [LICENSE](LICENSE).
