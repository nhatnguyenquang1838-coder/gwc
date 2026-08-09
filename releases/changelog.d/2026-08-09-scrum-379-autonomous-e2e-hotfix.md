# SCRUM-379 — autonomous E2E pre-prod + immutable main promotion hotfix

Adds deterministic runtime decisions for DAG READY selection, replay-safe claim intent,
manifest-scoped implementation (including Node Architect implementation files that do not
overlap the immutable active authority plane), exact-head pre-prod merge eligibility, and
immutable DAG-cut promotion decisions.

Invariant: `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`.

Child deliveries may merge autonomously only to `pre-prod`. A completed and integration-green
promotion set may create an immutable promotion branch pinned to one `preprod_cut_sha` and a
Draft PR to `main`. Autonomous ready-for-review and merge-to-main remain forbidden.
