# SCRUM-367 — Approval expiry recovery NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `failure_recovery.approval-expiry-recovery` from a historical SCRUM-244
M5 utility (`tools/node_architect/approval_expiry_recovery.py`) to an
instruction-backed executable NA81 node with current-task test evidence. Expired
approvals are now verified to stop all continuation, preserve audit evidence,
checkpoint the current state, and require exact scope/head reapproval when
continuation is legal. Replay detection, stale-continuation rejection, and
deterministic digest stability are also explicit.

## Guardrails

```text
EXPIRED_APPROVAL_IS_UNUSABLE.
REAPPROVAL_MUST_BIND_CURRENT_SCOPE_HEAD.
RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY.
```
