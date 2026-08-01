# F3 repo_delivery B1 M5 replay-safe slice

Tasks:
- SCRUM-193 — repo_delivery.branch-creation — M2 -> M5
- SCRUM-194 — repo_delivery.base-drift-check — M2 -> M5
- SCRUM-195 — repo_delivery.scoped-file-write — M2 -> M5

Changes:
- Add pure replay-safe decision helpers for guarded branch creation, base drift, and scoped file writes.
- Add Draft 2020-12 decision schemas.
- Add focused tests for idempotency, pending-action handling, stale base invalidation, out-of-scope rejection, unknown external outcomes, duplicate-effect replay, and authority boundaries.
- Add task-scoped G2/G3 gate records for the B1 fastlane.

Authority boundary:
- No merge, deployment, release, production config/data, credentials, migration, force-push, branch deletion, PR base change, audit-completion, or scale authority.
