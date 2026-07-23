# `scale_control` node family

Batch 09 is the final controlled catalog family. It defines batch admission, sequential throttling, exact-head observability, cardinality readiness, and independent-audit handoff.

## Boundaries

- Exactly nine descriptors.
- Canonical G3 control nodes use `g3_required` and remain bound exactly to `G3_PR`.
- Canonical G5 evidence/control nodes use `g5_required` and remain bound to `G5_DEPLOY`.
- `workflow-run-observability` and `rollout-progress-projection` are `audit_projection` nodes with `authority_boundary: read_only`; their gates are applicability metadata only.
- No scheduler, worker, connector implementation, deploy, release, production configuration/data, secret, credential, migration, or merge authority is introduced.
- Completing 81 descriptors means **ready for independent audit**, not production scale permission. `scale_81_nodes_allowed` remains `false` until a separately governed audit decision changes it.

## Nodes

1. `batch-admission-check`
2. `batch-size-limit-check`
3. `previous-batch-g5-verification`
4. `catalog-cardinality-readiness`
5. `execution-throttle-control`
6. `workflow-run-observability`
7. `exact-head-readiness-check`
8. `rollout-progress-projection`
9. `independent-audit-handoff`

## Backlog trace

Connector implementation for post-merge push-run discovery is tracked separately in Jira `SCRUM-69`; this batch models observability semantics only.
