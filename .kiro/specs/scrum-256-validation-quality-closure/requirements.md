# SCRUM-256 — SCRUM-256 validation-quality closure requirements

## Objective

Close the active Client runtime → CI → checkpoint → evidence → quality → G3 vertical slice with deterministic tests and lane evidence.

## Functional requirements

1. Decisions bind task, repository, branch, base SHA, exact head SHA, scope hash, graph revision, and idempotency key.
2. Evidence quality requires terminal exact-head CI success, schema-valid review receipt, same task/repository/PR/head/scope, read-only reviewer evidence, zero open findings, and non-stale timestamps.
3. G3 PASS requires the SCRUM-215 decision to PASS, all required validations to PASS for the same head, no unresolved findings, and current Ready-for-Review eligibility evidence.
4. Missing, stale, conflicting, malformed, or SHA-mismatched evidence fails closed with a closed reason-code set.
5. Replay of identical input is deterministic and grants no merge, deployment, or production authority.
6. Client runtime invokes real handlers in the allowlisted sequence and returns a typed terminal result only after both nodes PASS.

## Non-goals

F9 scale control, SCRUM-258 recovery, package/export, projection work, merge, deploy, release, runtime reload, production configuration/data, credentials, secrets, and migrations.
