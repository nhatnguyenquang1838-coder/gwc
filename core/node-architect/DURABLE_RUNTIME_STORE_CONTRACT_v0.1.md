# Durable Runtime Store Contract v0.1

Status: contract-only
Scope: SCRUM-105 / P2-K1

## Purpose

This contract connects the existing `RUNTIME_KERNEL@0.1`, runtime event,
checkpoint, transition-envelope, and node-pack primitives into one durable
store boundary. It defines logical operations and correctness rules for future
implementations. It does not implement a worker, scheduler, adapter, database
client, or migration.

## Canonical records

- A **run** is version-pinned and binds `run_id` to one task, repository, gate,
  runtime version, node-pack version, and current checkpoint.
- An **event** is append-only. Its `event_id`, `sequence`, predecessor, actor,
  node, gate, outcome, and evidence references make gaps and reordering
  detectable.
- A **checkpoint** is the canonical resume point. It records the current node,
  next node, exact next action, gate, scope hash, pending actions, revision,
  lease owner, expiry, and fencing token.
- A **pending action** is the durable boundary around an external operation.
  Unknown outcomes remain unresolved until deterministic readback evidence is
  recorded.

The JSON Schemas under `schemas/runtime/` are the machine-readable source for
these records:

| Record | Schema |
| --- | --- |
| run | `durable-run.schema.json` |
| event | `durable-event.schema.json` |
| checkpoint | `durable-checkpoint.schema.json` |
| pending action | `pending-action.schema.json` |
| adapter envelope | `adapter-contract.schema.json` |
| storage migration | `storage-migration.schema.json` |

## Logical store API

An implementation must expose provider-neutral operations with equivalent
semantics on the SQLite pilot and future PostgreSQL/Supabase backends:

1. `create_run(run)` creates one version-pinned run and its initial event.
2. `append_event(event)` appends exactly once by `event_id` and rejects a
   sequence or causal predecessor conflict.
3. `read_run(run_id)` and `read_events(run_id, after_sequence)` return the
   canonical run and ordered event history.
4. `read_checkpoint(run_id)` returns the current checkpoint and revision.
5. `cas_checkpoint(run_id, expected_revision, next_checkpoint)` commits only
   when the stored revision equals `expected_revision`; otherwise it returns a
   CAS mismatch without overwriting state and appends no success event.
6. `acquire_lease`, `renew_lease`, and `release_lease` manage one lease owner.
   Every successful acquisition increases the fencing token. A stale token
   cannot mutate a run, even when its lease has not yet been observed as
   expired by the worker.
7. `create_pending_action` persists an idempotency key before an adapter call.
   `read_pending_action` and `record_readback` reconcile the external outcome.

All writes that advance a run must be transactionally coupled to the event or
checkpoint evidence they claim. A provider may use different SQL transactions,
but it must preserve the observable ordering and atomicity above.

## Suspend, retry, and readback rules

- Checkpoint before suspend: persist the exact next action before emitting a
  wait, approval request, handoff, or connector-unavailable state.
- Reconcile before retry: an unknown, timeout, or transport-failed external
  result keeps the pending action open. Retry is forbidden until readback
  determines whether the original operation took effect.
- No false PASS: a node may report terminal success only when checkpoint state,
  live readback state, expected exit, lease/fencing state, and evidence agree.
- Version pin: node/runtime version drift is a typed failure. Resume must use
  the pinned version or start a new run; it must not silently reinterpret state.

## Adapter boundary

Every adapter request carries the run, checkpoint revision, fencing token,
node/version, gate, scope, and stable idempotency key. Results distinguish
success, blocked, retryable failure, permanent failure, unknown external
outcome, version mismatch, and fencing rejection. Side-effect adapters must
declare readback capability; a side-effect success requires confirmed readback
evidence.

## SQLite pilot to PostgreSQL/Supabase path

The migration contract is provider-neutral and intentionally non-executable:

1. Freeze and version the logical contract.
2. Probe compatibility and record schema/constraint differences.
3. Backfill or dual-write only under a separately approved migration scope,
   then verify counts, ordering, revisions, leases, fencing tokens, and event
   hashes.
4. Compare dual reads against the canonical source and retain rollback
   evidence.
5. Cut over only after exact readback and the applicable G6 authority; retain
   the pilot until the rollback window closes.
6. Retire the pilot only after a separate decision and verified evidence.

No phase authorizes production configuration, credentials, production data,
live migration, deployment, merge, or release. Those actions remain separate
GWC gates.

## Compatibility

This is an additive contract. Existing `schemas/node-architect/*` records remain
valid and are reused by reference in future adapters. The contract does not
expand the node catalog or grant any authority beyond the existing G0-G6
lifecycle.
