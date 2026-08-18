# Issue → spec → implementation/test traceability

Source requirement: GitHub issue #467 / Jira SCRUM-554.

| Issue AC | Requirement | Plan | Planned verification |
|---|---|---|---|
| AC1 | Direct action authority insufficient when child effect exceeds authority | Step 4 | Scenario 2 |
| AC2 | Read-only/compute child does not spuriously escalate | Step 4 | Scenario 3 |
| AC3 | Cross-repo mutating child requires independent authority | Step 4 | Scenario 4 |
| AC4 | Capability semantics machine-readable, not inferred solely from gate labels | Steps 1, 7 | Scenario 12 |
| AC5 | Effect/evidence identity deterministic, digest-bound and replay-safe | Steps 2, 3, 5 | Scenarios 1, 9 |
| AC6 | PR-head checks cannot satisfy merge-SHA evidence | Step 5 | Scenario 5 |
| AC7 | Historical successful automation never becomes authority | Step 5 | Scenario 6 |
| AC8 | Compatible direct-action packets remain valid when no unauthorized transitive mutation exists | Step 3 | Scenarios 10, 11 |

Additional spec hardening from independent review:
- conditional mutating effects: Step 2 / Scenario 7;
- retention deletion => destructive capability: Steps 1, 6 / Scenario 8.
