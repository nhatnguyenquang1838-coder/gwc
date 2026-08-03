# SCRUM-208 Design — CAS Write Guard M5

## Components
- `cas_write_guard.py`: pure deterministic evaluator; no connectors or side effects.
- `cas-write-guard-result.schema.json`: closed result contract.
- `checkpoint_store.py`: optional strict `cas_context` integration plus a bound idempotency ledger.

## Canonical binding boundary
`CheckpointInput` is authoritative for task, repository, branch, protected base,
scope, expected revision, checkpoint identity, lease ID, and fencing token.
Caller-supplied `cas_context` cannot replace those values. Conflicting expected
or observed static bindings fail closed before mutation. Existing store binding
is authoritative after the first strict checkpoint; compatible legacy checkpoint
records may supply the binding when the explicit store binding is absent.

## Decision order
1. Validate required typed input and integration preconditions.
2. Check task/repository/branch/scope bindings.
3. Check protected-base SHA.
4. Check lease owner and token.
5. Check fencing token.
6. If an idempotency effect exists, verify its exact task/repository/branch/base/
   scope/checkpoint/lease/fencing/idempotency ownership binding.
7. Return an exactly bound committed effect. Revision advance and later lease
   expiry are tolerated only for this proven crash-after-write replay.
8. For a new effect, check lease expiry.
9. Check expected versus observed revision.
10. Permit exactly one monotonic write and persist the effect ownership binding.

All rejects route to `runtime_checkpoint.state-reconciliation`; no reject permits
blind retry. Legacy callers without `cas_context` continue to use the existing
revision-only guard.
