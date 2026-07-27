# SCRUM-121 Design — Replayable E2E Pilot

The pilot records a typed run history made of nodes, decisions, evidence bindings, side-effect keys and projection receipts. The validator checks that each side effect has an idempotency key, each provider artifact has an immutable version or SHA, and each replay decision either matches the original route or records a typed live-state divergence.

The design intentionally avoids a live product release. GitHub branch/PR/CI evidence is used for repository truth, while Jira, Slack and Notion are reconciliation projections.
