feat(gwc): SCRUM-345 NA81-F6 external-audit-event-projection stale-source guard

Implement the missing SCRUM-345 (NA81-F6-N03) behavior on top of the existing
sync_projection external-audit-event-projection renderer. The SCRUM-222 M4
`project_external_audit_event` renders canonical-source, stable correlation,
idempotent duplicate replay, privacy-boundary and non-authority semantics, but
it lacked a stale-source check: a source-authority decision that is
digest-valid yet observed against an outdated canonical snapshot was still
rendered READY.

New behavior (DELTA_REQUIRED, backward-compatible — `project_external_audit_event`
is unchanged):

- `project_external_audit_event_na81(...)` delegates all canonical rendering,
  correlation, idempotency, privacy and non-authority semantics to
  `project_external_audit_event` and adds `source_freshness_cutoff`.
- A source-authority decision that is digest-valid but was observed before
  `source_freshness_cutoff` (the canonical source's known-current freshness
  timestamp) is rendered BLOCKED with `EXTERNAL_AUDIT_SOURCE_STALE` instead of
  READY. Without a cutoff the wrapper is behavior-identical to the base.
- New reason code `EXTERNAL_AUDIT_SOURCE_STALE` appended to `REASON_PRECEDENCE`;
  surfaced distinctly from a structurally invalid source.
- Read-only; every authority field fixed to false; `read_only_projection` true;
  no connector call, network request, filesystem mutation, Jira, branch, commit,
  PR, approval, merge, deployment, release, or production operation. Never
  projects secrets/credentials or derives truth from another projection.

New files:
- tests/test_external_audit_event_projection_na81.py (12 NA81 projection tests)

Updated files:
- tools/node_architect/external_audit_event_projection.py (project_external_audit_event_na81, _observed_at_dt)

All authority fields are fixed to false; read_only_projection is fixed to
true. Validators: SYNC_PROJECTION_NODE_CATALOG_VALID (F6), external-audit-event
schema (additionalProperties:false) satisfied, 12/12 NA81 unit tests pass,
full `python3 -m unittest discover -s tests` green.

Related: SCRUM-345 (#280), Epic SCRUM-288, Family SCRUM-294. Predecessors
SCRUM-350/351; consumer SCRUM-347. Delivers to pre-prod only; main FORBIDDEN.
Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-345.
