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
