# Dataspace core (V0)

Provider-neutral source-declared datasets, layouts and explicit immutable runtime mounts.
No Cockpit, ROBA, CLI, shell, persistence catalog or registry is part of this module.

A dataset field names an **immediate-owner composition dependency**, not a global type:

```toml
[dataset]
id = "session"
[fields.cwd]
contract = "path"
operations = ["get", "set", "delete"]
[fields.timeout]
contract = "number"
operations = ["get", "set"]
default = 5.0
```

The dependency exposes `process_input(value)` (consumer -> native storage) and
`process_output(value)` (storage -> consumer). Different owners may give the same alias different
meanings. Input/output representations need not be identical. Defaults are in consumer form,
canonicalized once through both boundaries and never written. Only genuine Nolspace missing keys
activate defaults. Native values are finite string/integer/number/boolean/null/array/object;
bool is not integer. Non-native recursive data and cycles are rejected before any write.

A layout only names dataset dependencies, with no nesting or flattening:

```toml
[layout]
id = "runtime"
[sets]
session = "session"
project = "project"
```

`dataset` and `layout` take `config = { model = "owner-relative.toml" }`. Absolute paths,
escaping paths/symlinks, unknown properties, duplicates and invalid operations fail. IDs are
non-empty strings; dependency aliases are flat identifiers. The source is read once, definitions
are immutable and `describe` returns fresh metadata without default values.

DIX finalizes immediate-owner bindings after constructing the graph. Therefore definition/default
materialization is an explicit **post-binding** phase (`definition()`), not a constructor callback
or Core hook. Runtime materialization uses these local definitions; no runtime registry exists.

## Materialize and consume

The immediate owner declares its contract dependencies, datasets (`session`, `project`),
`layout`, provider (`backend`, exposing all four Nolspace operations), and this factory:

```toml
[compositions.factory]
use = "skaldos/stores/dataspace/core/runtime"
config = { layout = "layout", providers = ["backend"] }
```

After DIX has built the graph, the owner's wrapper calls:

```python
space = factory.materialize([
    {"set": "session", "provider_alias": "backend", "nolspace_view": session_view},
    {"set": "project", "provider_alias": "backend", "nolspace_view": project_view},
])
space.describe()
space.set("session", "cwd", "/tmp/work")
space.get("session", "cwd")
space.delete("session", "cwd")  # {"set": "session", "field": "cwd"}
```

The ordered mount list makes duplicate roles an explicit error rather than silently overwriting
them. Every role must appear exactly once, with only `set`, `provider_alias`, `nolspace_view`.
Provider aliases bind only exposed functions of immediate-owner dependencies, never a registry.
Views and default snapshots are detached behind private copy-returning closures; definitions,
mount entries, provider bindings and the four-method handle are immutable. Changing source files,
input mounts, view targets, returned metadata or default values cannot retarget a live handle.

`describe` performs no provider call and includes no target, token, stored value or default value.
`get` performs one lookup; only the graph-local `NolspaceNotFoundError` activates its prevalidated
default. `set` validates/transforms input, upserts exactly once and decodes the provider's return,
not a local guess or re-read. Output failure after a successful write does not undo that write.
`delete` performs exactly one deletion, no lookup. Unknown fields/sets and forbidden dataset
operations fail locally. View caps and authenticated provider rights can only narrow operations.
Errors other than genuine Missing are not caught or converted by Dataspace.

No values are cached in the handle, no default is written, no role has an implicit local backing,
and no alias/mapping, partial update, transaction, rollback, synchronization or audit is promised.
Composition graph lifetime remains caller-owned: destroy instances, then unload their modules.
Do not keep calling a returned handle after destroying its owning graph.

## Runnable reference graph

`tests/fixtures/dataspace_roba/compositions/consumer/` is a source-declared integration owner: `path`,
`number`, `color` are local contracts, two Dataset definitions feed the `runtime` Layout, and
one explicit `roba` dependency supplies Nolspace effects. `private` and `evia` handles reuse
that exact graph while their mount tables select different project Instances and the same
session Context values view. The consumer never sees the bootstrap/provider APIs.

`tests/test_dataspace_roba_e2e.py` independently checks native target values, missing-default
nonmaterialization, shared sessions, project isolation, invalid colors, read-only fields,
authenticated rights, explicit bad credentials and complete process/socket/loader cleanup.
`tests/probes/dataspace_delivery_probe.py <module-root> <source|wheel>` exercises the same
contract with clean source or isolated delivered module roots. No Cockpit installer changes
are needed or intended: these external roots are explicitly loaded by their consumer.
