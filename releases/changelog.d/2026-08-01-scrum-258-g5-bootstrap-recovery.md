# SCRUM-258 — authorized G5 bootstrap recovery

- Extend the canonical G4/G5 evidence workflow with an exact human recovery command for immutable merged bootstrap PRs.
- Verify merged PR metadata, original G4 provenance in the merge commit, exact successful main-push workflow run IDs, approver permission, expiry, and source receipt digest.
- Add fail-closed recovery schema, validator, template, negative tests, idempotency, conflict rejection, canonical Actions artifacts, and explicit recovery-mode PR traces.
- Preserve normal event-driven G4/G5 behavior, projection-only Jira/Slack semantics, and the 81-node runtime catalog.
