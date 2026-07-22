# REVAMP-GWC-016 — intake context node family batch

```text
Task: REVAMP-GWC-016
Family: intake_context
Batch: batch-01-intake-context
Node count: 9
Authority boundary: G0_CONTEXT
```

## Added

- Added the first controlled catalog batch with 9 `intake_context` runtime node definitions.
- Added a family README for request intake, source resolution, repo identity, protected-base capture, risk classification, read/write scope, intake-card rendering, and context-gap escalation.
- Added a stdlib validator for the `intake_context` node family.
- Added regression tests for valid family count, G0-only gate boundaries, max-node enforcement, and authority-boundary rejection.

## Not included

- No all-81 node implementation.
- No runtime engine, scheduler, worker, storage adapter, deploy, release, production config/data, secrets, credentials, or migration.
