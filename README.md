# Skaldos DIX modules

External, explicitly composed modules for [DIX](https://github.com/skaldos/dix).

The `sway` branch is a focused architecture branch. It currently ships only two independently
loadable Sway modules:

```text
sway/core  -> policy-free Sway IPC
sway/nav   -> navigation algorithms, runtime binding, applications and delivery
```

It deliberately does not ship the earlier group, theme, ROBA, Wofi or profile experiments. Their
history remains on `main` and may return later as separate modules instead of rebuilding one
monolith.

Start with the [English Sway guide](sway/README.md) or the
[German Sway guide](sway/README.de.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
