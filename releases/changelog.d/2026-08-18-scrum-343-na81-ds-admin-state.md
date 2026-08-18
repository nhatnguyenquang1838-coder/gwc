feat(gwc): SCRUM-343 NA81-F6 ds-admin-state-projection bounded render + NA81 semantics

Implement the missing SCRUM-343 (NA81-F6-N01) NA81 semantics on top of the
existing sync_projection ds-admin-state-projection renderer. The SCRUM-220
`project_ds_admin_state` only performs the closed read-only projection; it
lacked the explicit SCRUM-343 assertions (stale-source-revision defense,
deterministic/idempotent replay, privacy allowlist filtering, explicit
non-authoritative guarantee, missing-canonical-source block).

New behavior (DELTA_REQUIRED, backward-compatible -- `project_ds_admin_state`
is unchanged and reused as the projection core):

- `project_ds_admin_state_na81(...)` reuses `project_ds_admin_state` and adds:
  * stale source revision detection -- a source-authority decision whose
    canonical bindings are STALE / MISSING / AMBIGUOUS / CONFLICT is blocked
    (DS_ADMIN_NA81_STALE_SOURCE_REVISION); the projection never renders from
    non-current evidence;
  * deterministic / replay idempotency -- identical inputs yield an identical
    projection_digest (na81.idempotent);
  * privacy filtering -- only ALLOWED_CANONICAL_KEYS may appear in the
    projected canonical state; every other field is dropped;
  * explicit non-authoritative guarantee -- read_only_projection fixed true,
    every authority field fixed false; the projection is never canonical task
    truth (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH);
  * missing canonical source -- an envelope without canonical_state is
    BLOCKED (no projection from absent truth).

New files:
- tests/test_ds_admin_state_projection_na81.py (NA81 semantics tests)

Updated files:
- tools/node_architect/ds_admin_state_projection.py (project_ds_admin_state_na81)

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-343.
Targets pre-prod only; main is FORBIDDEN.
