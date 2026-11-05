# Nolspace Core — Named Object Lookup Space

Explicit module ID: `skaldos/stores/nolspace/core`. Load `dix/norn` first.

`contract.reference/object/view` validate detached native data through existing Norn Strands.
Reference: `{name}`. Object: `{name,type,value}`. A `nolspace` object's value contains `caps`
(a subset of enumerate/lookup/upsert/delete) and optionally a provider-opaque object `target`.
Standard types: string/integer/number/boolean/null/array/object/nolspace. Provider-defined names
pass as native data; they do not gain generic editing semantics. Values must be finite native
data, not arbitrary runtime objects. Names are preserved, never translated or guessed.

The `api` composition exposes **only** enumerate/lookup/upsert/delete. Pass one explicitly bound
local Composition API plus a View to each operation. This is capability injection, not a remote
provider name, registry or automatic implementation discovery. Only these literal functions are
called. A Child returned by lookup keeps the same provider; core never interprets target.

Enumerate returns References, never calls lookup and resolves no values. Upsert/delete never
read first. Missing view caps fail before provider invocation; providers must still enforce
native authority on every operation. There is no identity conflict resolution, fallback, sync,
enter, grant, copy, move, patch or execution protocol. `contract` is validation, not an extra
backend operation. Root/bootstrap belongs to a provider-specific composition, not the standard.

## Missing keys

Only genuine absence is `NolspaceNotFoundError`. Obtain the loader-local exception class from
an explicit `skaldos/stores/nolspace/core/contract` dependency:
`missing = contract.require("not_found_type")()`. Catch that class around `api.lookup(...)`.
The four positive API operations are unchanged. Other errors must not become defaults or missing
keys. Exception identity is scoped to the loaded module graph; no global registry/import hook is
required. Unload the graph through the normal DIX lifecycle.
