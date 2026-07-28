# Task Me FastLane plan: SCRUM-150

This is a single-task, evidence-backed implementation plan for the P2-to-P5
cross-phase replay, authority and outcome regression. The plan is based on the
observed protected-base candidate `origin/main` at
`6c2b6ac273b0d0d23a31e311b081d2cefd9aa9be`.

The prior SCRUM-146–149 evidence references an older base and is therefore
treated as stale input that must be detected and classified, not as current
gate truth. Jira is used for traceability only; `.gwc/tasks/SCRUM-150/` and
exact repository/CI evidence remain authoritative for the governed gates.

## Delivery boundary

The intended change is a provider-neutral validator, positive and rejected
cross-phase fixtures, focused tests, and task-scoped evidence. It does not
authorize merge, deploy, release, production data, credentials, or automatic
promotion. G4, G5 and G6 remain separate human-controlled gates.

## Delivery order

1. Rebaseline dependency evidence against the exact current protected base.
2. Implement the smallest cross-phase record validator using existing durable,
   replay, P5 and exact-head contracts.
3. Add positive and negative fixtures for stale envelopes, projection leakage,
   replay divergence, metric fabrication, and human-authority violations.
4. Run focused validation, inspect the complete diff, and stop at G3 pending
   the user's exact approval for any later gate.
