# Design Document

## Overview

Add a contract-only durable runtime layer under the existing `schemas/runtime`
and `core/node-architect` ownership boundaries. Reuse the existing node-
architect `runtime-event`, `checkpoint`, `transition-envelope`, `node-pack`,
and `RUNTIME_KERNEL` concepts; extend them with explicit durable store,
pending-action, adapter, and migration contracts instead of creating a second
runtime authority.

## Architecture

```text
run schema
    |
append-only event schema --> store API contract --> SQLite adapter | future PostgreSQL/Supabase adapter
    |                                  |
checkpoint + CAS + lease/fencing <-- pending action + readback
    |
node request/result adapter contract
```

Canonical facts remain the run/event/checkpoint store. Jira, Slack, Notion,
dashboards, and generated projections remain non-authoritative. The contract
package does not execute adapters or migrations.

## Components and Interfaces

1. `schemas/runtime/durable-run.schema.json` — version pins, task/repository
   binding, lifecycle status, and current checkpoint reference.
2. `schemas/runtime/durable-event.schema.json` — immutable event identity,
   sequence/causal links, actor, gate, node, idempotency, and outcome.
3. `schemas/runtime/durable-checkpoint.schema.json` — revision, lease owner,
   fencing token, current/next node, exact next action, pending references, and
   suspend reason.
4. `schemas/runtime/pending-action.schema.json` — idempotency key, adapter
   operation, unknown-result state, readback requirement/evidence, and closure.
5. `schemas/runtime/adapter-contract.schema.json` — request/result envelopes,
   capability/version declarations, typed failures, and readback evidence.
6. `schemas/runtime/storage-migration.schema.json` — provider-neutral migration
   phases, compatibility checks, verification, rollback, and cutover evidence.
7. `core/node-architect/DURABLE_RUNTIME_STORE_CONTRACT_v0.1.md` — prose store
   API, transaction boundaries, invariants, and SQLite-to-PostgreSQL/Supabase
   migration sequence.
8. `tests/test_durable_runtime_contracts.py` — schema and invariant tests.

## Data Models

All models use `schema_version: 0.1`, UTC RFC 3339 timestamps, stable opaque
IDs, exact task/repository/gate binding, and explicit status enums. Checkpoint
revision is monotonic; lease fencing tokens are monotonic and invalidated on
lease replacement. Event sequence is append-only. Pending actions cannot close
without deterministic readback evidence.

## Correctness Properties

- CAS mismatch never overwrites the stored checkpoint.
- A stale lease or fencing token cannot advance a run.
- An unknown external result cannot be retried before reconciliation.
- Event sequence gaps and duplicate event IDs are detectable.
- A terminal adapter success for a side-effect node requires readback evidence.
- Storage-provider changes preserve logical operation names and state-machine
  semantics.
- No schema or contract grants G2/G3/G4/G5/G6 authority.

## Error Handling

Use typed outcomes for revision mismatch, lease expired, fencing stale,
idempotency conflict, unknown external result, readback mismatch, version drift,
and migration verification failure. Errors retain the affected run,
checkpoint, event, or pending-action reference and route to reconciliation or
fail-closed suspension. Do not blind-retry unknown side effects.

## Testing Strategy

Validate each JSON Schema with valid and invalid fixtures. Add cross-contract
tests for CAS/lease/fencing requirements, pending-action reconciliation, adapter
terminal-outcome rules, and provider-neutral migration phases. Run the existing
runtime schema and package validators plus the targeted test module.

## Implementation Constraints

- Contract/schema/test/release metadata only; no runtime loop or database code.
- Preserve existing `schemas/node-architect` contracts and package IDs.
- Reuse `RUNTIME_KERNEL@0.1` and existing checkpoint/event concepts.
- No production credentials, data, migration, deploy, release, merge, or
  protected-main write.
- Keep the guarded branch diff limited to the approved files.
