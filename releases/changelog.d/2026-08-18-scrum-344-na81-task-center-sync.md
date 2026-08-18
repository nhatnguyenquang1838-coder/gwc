feat(gwc): SCRUM-344 NA81-F6 task-center-sync deterministic sync intent

Implement the missing SCRUM-279 (#279) NA81 execution-level Task Center
sync intent on top of the existing sync_projection task-center-sync node.
The M4 `project_task_center_sync` renderer is a pure projection of B1
decisions + envelope; it lacked the SCRUM-279 deterministic sync intent
with three required properties:

- `render_task_center_sync_na81(...)` renders an explicit, read-only sync
  intent carrying a **monotonic source revision** that rejects
  out-of-order (`source_revision` regresses) and **stale** (same revision
  but canonical content mutated) sources.
- A **stable idempotency key** over canonical facts + revision so duplicate
  replay is a clean no-op (`SYNC_CURRENT`) rather than a fresh projection.
- An **explicit readback expectation** telling the consumer exactly what to
  read back (expected canonical state digest + revision + idempotency key).

Backward-compatible: `project_task_center_sync` is unchanged. Task Center
remains a projection surface -- it never becomes canonical task truth or
authority (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH); a projection failure
never mutates canonical outcome
(PROJECTION_FAILURE_DOES_NOT_MUTATE_CANONICAL_OUTCOME). All authority fields
are fixed to false; `read_only_projection` is fixed to true. No connector
call, network request, filesystem mutation, Jira transition, approval,
merge, deployment, release, or production operation.

New files:
- tests/test_task_center_sync_na81.py (14 NA81 sync-intent tests)

Updated files:
- tools/node_architect/task_center_sync.py (render_task_center_sync_na81)

Related: SCRUM-344 (#279), Epic SCRUM-288, Family SCRUM-294. Predecessors
SCRUM-350/351; consumer SCRUM-347.
