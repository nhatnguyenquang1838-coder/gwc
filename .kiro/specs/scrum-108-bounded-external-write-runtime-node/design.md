# SCRUM-108 Design — bounded external-write runtime node

## Approach
Add a pure Python runtime helper under `tools/node_architect/bounded_external_write.py` plus unit tests. The helper must not call Jira, GitHub, Slack, or any live provider. It classifies provided intent, adapter result, and readback evidence into deterministic states.

## Core model
- `BoundedWriteIntent`: task id, repository, run id, checkpoint revision, lease/fencing token, scope hash, idempotency key, operation, payload hash, persisted flag.
- `BoundedWriteReadback`: observed effect count, matched idempotency key, matched scope hash, external reference, evidence refs, status.
- `BoundedWriteDecision`: state, dispatch_allowed, retry_allowed, repeat_dispatch_allowed, human_required, reason, evidence packet.

## Non-goals
No live connector calls, no provider SDK, no repository mutation outside approved files, no production data, no deployment, no merge.
