# SCRUM-119 Requirements

## R1 — Exact invocation binding
Every request binds task ID, repository, base/head SHA, procedure ID/version, adapter version, GWC scope hash and idempotency key.

## R2 — Permission-before-side-effect
The adapter validates allowed actions and paths before any write. Denied paths, gate approvals, scope expansion and projection writes are rejected.

## R3 — Canonical authority separation
BMAD cannot approve G2/G4/G5/G6, mutate `.gwc`, merge, deploy, release, change secrets or perform production operations.

## R4 — Bounded procedures
The registry covers architecture analysis, story preparation, TDD implementation, code review and release-readiness checks. Each procedure declares mode, inputs, outputs, allowed actions, timeout and retry policy.

## R5 — Result provenance
Every result returns status, evidence references, changed paths, tests/checks, findings, residual risks, exact provenance and a read-only recommendation.

## R6 — Idempotency and resume
Repeated idempotency keys cannot duplicate side effects. Interrupted work resumes only from a compatible checkpoint bound to the same request digest and scope hash.

## R7 — Explicit unpublished provider state
BMAD `ready-unpublished` is valid only with pinned source repository, source commit and adapter version. No implicit latest resolution is allowed.

## R8 — Failure taxonomy
The contract distinguishes invalid input, scope violation, unsupported procedure, partial result, tool unavailable, stale checkpoint and duplicate idempotency key.
