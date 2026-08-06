## 2026-08-06 — SCRUM-171 sync_projection B2 target-projection runtime renderers (M4)

### Added

- Closed `schemas/sync-projection-envelope.schema.json` shared input contract consumed by all three B2 target projections.
- `tools/node_architect/ds_admin_state_projection.py` (`project_ds_admin_state`) — pure, read-only DS Admin state projection renderer (SCRUM-220).
- `tools/node_architect/task_center_sync.py` (`project_task_center_sync`) — pure, read-only Task Center sync projection renderer (SCRUM-221).
- `tools/node_architect/external_audit_event_projection.py` (`project_external_audit_event`) — pure, read-only external audit-event projection renderer (SCRUM-222).
- Closed per-target result schemas: `ds-admin-state-projection`, `task-center-sync-projection`, `external-audit-event-projection`.
- Focused behavior tests `tests/test_sync_projection_m4_batch_b2.py` (SCRUM-220/221/222) covering readiness, closed-schema validity, source-authority/evidence/privacy mismatch, prior-binding regression and NOOP readback.
- Family validator runtime-binding extension asserting each B2 node maps to exactly one closed schema, one pure evaluator, fixed `read_only_projection: true` and authority fields `false`.
- README M4 runtime-binding documentation for the three target-projection nodes.

### Safety

- This fragment documents SCRUM-220/221/222 only.
- These renderers perform no connector call, network request, filesystem mutation, Jira transition, branch/PR/approval/merge/deploy/production operation; every runtime artifact fixes `read_only_projection: true` and all authority fields to `false`.
- This change grants no protected-branch write outside G2, merge, auto-merge, deploy, release, production configuration, credential, migration, production-data, force-push, branch-deletion, or PR-base-change authority.
