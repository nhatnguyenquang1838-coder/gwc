# SCRUM-377 — Rollout progress projection NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.rollout-progress-projection` from a historical SCRUM-254
M4 renderer (`tools/node_architect/rollout_progress_projection.py`) to an
instruction-backed executable NA81 node with current-task test evidence. The
projection is deterministic, non-authoritative, and derives only from verified
canonical current-task completion plus exact merge/G5 evidence. UNKNOWN, BLOCKED
and PENDING stay explicit; unsafe Jira Done or historical implementation never
counts as completed.

## Guardrails

```text
ROLLOUT_PROGRESS_IS_NON_AUTHORITATIVE_PROJECTION.
ONLY_VERIFIED_CURRENT_TASK_DELIVERY_COUNTS_AS_COMPLETE.
SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY.
```
