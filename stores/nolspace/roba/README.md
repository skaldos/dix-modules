# ROBA Nolspace provider

Explicit module ID `skaldos/stores/nolspace/roba`; load dix/state, dix/cli, dix/norn, dix/roba,
then the Nolspace core and this module. No Cockpit, VisiData or tmux imports.

`connection` is provider-specific bootstrap (draft/validate/root), not extra standard verbs.
It accepts existing explicit canonical Context/Instance connections, using a token or an existing
native capability socket. No automatic Control/owner/environment resolution or access creation. Root inspection
reads authenticated metadata only. `provider` exposes exactly enumerate/lookup/upsert/delete.
Consume it through the explicit core/api binding; children retain the same provider.

Context roots expose separate values/instances children, so equal key/Instance names cannot
collide. Instance roots directly expose values. Read -> enumerate/lookup, write -> upsert/delete;
native owner authority is retained. Each operation re-inspects authenticated rights, never trusts
caller-modified caps. Structural Instance discovery uses native metadata-only listing if allowed,
or known scopes from principal.access when Context-read is absent. This grants no new native
listing permission. Value enumeration uses the completed UP-070 keys-only DIX composition.

Upsert accepts all seven standard types: string, integer, number, boolean, null, array, object.
It replaces one complete native value through exactly one data.set, returning the submitted value
without reading before/after. Malformed values, nolspace and unknown types are rejected before
transport. Whole-value atomicity, normalization and concurrent writers remain provider-owned;
there is no nested-path, patch, merge or CAS API. Delete acts on one key. Native errors remain visible with credential
redaction; there is no fallback, sync, schema inference, grant management or resource creation.
