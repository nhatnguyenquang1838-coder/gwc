# SCRUM-208 — runtime_checkpoint.cas-write-guard M5

- Added a typed, deterministic CAS decision bound to task, repository, branch,
  base SHA, scope, revision, lease owner/token/expiry, fencing token, observed
  state, checkpoint identity, and idempotency identity.
- CAS, lease, owner, fencing, base, and scope mismatches fail closed with latest
  state evidence and an explicit SCRUM-209 reconciliation route.
- Strict checkpoint integration now treats `CheckpointInput` and persisted store
  binding as authoritative; conflicting caller context is rejected before mutation.
- Committed effects now persist exact task/repository/branch/base/scope/checkpoint/
  lease/fencing/idempotency ownership and replay only after that binding is proven.
- Exactly bound crash-after-write replay may tolerate the committed revision advance
  or later lease expiry without appending another runtime event.
- Added adversarial regression coverage for context substitution, idempotency-key
  collision, unbound legacy effects, and stale lease/fencing replay attempts.
- Preserved the legacy revision-only API for callers that do not supply `cas_context`.
- No merge, deploy, release, production, credential, migration, or G6 authority
  is introduced.
