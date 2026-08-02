# Node instruction contract and universal evidence ledger

Task: `SCRUM-263`

- Adds instruction-backed execution contracts for the four-node G2 repository-write route.
- Adds fail-closed validation for instruction, evidence, logs, next route, workflow mode, and authority boundaries.
- Adds canonical replay-safe task/run/node evidence ledger records and runtime event digests.
- Enforces `MODE_DOES_NOT_BYPASS_NODE_RUNTIME` for normal, fastlane, e2e, hotfix, and rescue modes.
- Preserves separate G2-G6 authority and projection-only Jira/Slack/Notion boundaries.
