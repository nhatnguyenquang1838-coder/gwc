# SCRUM-208 Design — CAS Write Guard M5

## Components
- `cas_write_guard.py`: pure deterministic evaluator; no connectors or side effects.
- `cas-write-guard-result.schema.json`: closed result contract.
- `checkpoint_store.py`: optional strict `cas_context` integration plus idempotency ledger.

## Decision order
1. Validate required typed input.
2. Return an already committed idempotent effect.
3. Check task/repository/branch/scope bindings.
4. Check protected-base SHA.
5. Check lease owner, token, and expiry.
6. Check fencing token.
7. Check expected versus observed revision.
8. Permit exactly one monotonic write.

All rejects route to `runtime_checkpoint.state-reconciliation`; no reject permits blind retry.
Legacy callers without `cas_context` continue to use the existing revision-only guard.
