# SCRUM-208 — runtime_checkpoint.cas-write-guard M5

- Added a typed, deterministic CAS decision bound to task, repository, branch,
  base SHA, scope, revision, lease owner/token/expiry, fencing token, observed
  state, and idempotency identity.
- CAS, lease, owner, fencing, base, and scope mismatches fail closed with latest
  state evidence and an explicit SCRUM-209 reconciliation route.
- Added commit-before-response replay protection: a committed idempotency key
  returns canonical readback without appending another runtime event.
- Integrated strict CAS context into checkpoint persistence while preserving the
  legacy revision-only API for existing callers.
- No merge, deploy, release, production, credential, migration, or G6 authority
  is introduced.
