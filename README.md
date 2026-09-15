# Skaldos DIX Modules

External source modules maintained by Skaldos for
[DIX](https://github.com/skaldos/dix).

[Deutsch](README.de.md) · [DIX](https://github.com/skaldos/dix) ·
[ROBA](https://github.com/skaldos/roba) ·
[`skaldos/sway` guide](sway/README.md)

> **Public Alpha:** the modules are tested and usable, but their source contracts and setup may
> still change. Pin repository revisions for repeatable use.

## What this repository is

Each top-level module directory is a directly loadable DIX module root. When this repository is
cloned as `dix/modules/skaldos`, the directory `sway/` is loaded explicitly with module ID
`skaldos/sway`:

```text
workspace/
├── roba/
└── dix/
    └── modules/
        ├── dix/             # modules shipped by DIX
        └── skaldos/         # this repository
            └── sway/        # external module skaldos/sway
```

This repository is a source-module library. It is deliberately **not** a Python distribution, DIX
package manager, module registry, Git submodule, or automatic installer. Every module keeps its
own dependencies, tests, optional integrations, and release decisions.

## Available modules

### `skaldos/sway`

A real external DIX consumer for topology-aware Sway window-group navigation:

```text
Sway IPC
+ ROBA coordination state
+ DIX compositions/applications
+ fixed low-latency keybindings
+= topology-aware window-group navigation
```

The module provides:

- explicit group management through DIX and ROBA;
- private file-owned window membership;
- narrow atomic route and active-member projections for navigation;
- native-direction, topology-aware group navigation;
- a dependency-light direct navigation entry;
- optional Wofi adapters and a Sway configuration fragment.

Read the full [English setup guide](sway/README.md) or the
[German setup guide](sway/README.de.md).

## Source assembly

The complete public example uses three sibling source repositories:

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

DIX is prepared before the external checkout is placed below `dix/modules`. This order keeps a
locally built DIX distribution limited to the modules owned by its committed source; directories
already present below `modules/` are build inputs. The external checkout is then consumed from its
source path, not rebuilt as part of DIX.

DIX does not discover the checkout. The Sway application and its launchers pass both the source
path and module ID explicitly.

## Ownership boundaries

- **DIX** assembles local composition and application graphs. It does not ship Sway or `i3ipc`.
- **ROBA** provides ephemeral coordination state. It does not persist groups across daemon
  restarts and is not a credential store.
- **`skaldos/sway`** owns Sway IPC, group behavior, projections, direct navigation, dependencies,
  and desktop integrations.
- **The user** owns clone locations, process startup, local state paths, keybindings, and the
  operating-system access boundary.

Python loaded as a DIX module runs in the caller's process. Neither this repository nor DIX is a
security sandbox.

## Development

Use an explicit DIX checkout and install the module-owned dependency into its environment:

```sh
DIX_ROOT=/absolute/path/to/dix
MODULES_ROOT=/absolute/path/to/dix-modules

cd "$DIX_ROOT"
uv sync --frozen --extra dev --extra cli --extra state --extra roba
uv pip install --python .venv/bin/python -r "$MODULES_ROOT/sway/requirements.txt"

cd "$MODULES_ROOT"
DIX_REPOSITORY="$DIX_ROOT" "$DIX_ROOT/.venv/bin/python" -m pytest -q tests
uvx --from ruff==0.16.7 ruff check sway examples tests
"$DIX_ROOT/.venv/bin/python" -W error -m compileall -f -q sway examples tests
```

The test suite uses deterministic fakes at the Sway/i3ipc and Wofi boundaries. A successful test
run does not claim that a real desktop session was exercised.

## License

Apache License 2.0. See [`LICENSE`](LICENSE).
