# SCRUM-119 Design

## Components

```text
GWC invocation authority
  -> request schema validation
  -> permission preflight
  -> procedure registry lookup
  -> bounded BMAD executor
  -> result schema validation
  -> evidence/provenance return
```

GWC owns invocation authority and gate state. BMAD is an executor. DW-SuperApps may later package a thin host adapter but cannot redefine this contract.

## Modes

- `read_only_analysis`: no repository writes.
- `bounded_repository_write`: only declared paths/actions and only with matching G2 evidence.
- `prohibited`: gate approval, `.gwc` mutation, merge, deploy, release, secrets, migration, production and unowned projection writes.

## Enforcement order

1. Validate request structure and pinned provenance.
2. Resolve procedure/version from registry.
3. Compare task/repository/SHA/scope hash.
4. Validate permission envelope and normalized paths.
5. Reject before side effects on any mismatch.
6. Claim idempotency key and checkpoint lease.
7. Execute bounded procedure.
8. Validate result, changed paths and evidence.
9. Return read-only recommendation to GWC.

## Resume

A resume token binds request digest, procedure version, scope hash and checkpoint revision. Changed inputs invalidate the checkpoint instead of silently continuing.
