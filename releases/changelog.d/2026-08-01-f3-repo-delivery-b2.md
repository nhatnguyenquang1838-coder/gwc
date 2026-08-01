# F3 repo_delivery B2

Tasks:
- SCRUM-196 — repo_delivery.diff-readback — M2 -> M4
- SCRUM-197 — repo_delivery.draft-pr-creation — M2 -> M5
- SCRUM-198 — repo_delivery.ci-run-capture — M3 -> M5 remediation

Changes:
- Add replay-safe diff readback decision helper and schema.
- Add replay-safe Draft PR creation decision helper and schema.
- Add exact-head CI run capture decision schema and remediation gate records.
- Add focused B2 replay, drift, duplicate-outcome, and authority-boundary tests.

Authority boundary:
- No merge, deployment, release, production config/data, credentials, migration, force-push, branch deletion, PR base change, audit-completion, or scale authority.
