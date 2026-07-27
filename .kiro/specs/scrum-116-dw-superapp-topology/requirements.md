# SCRUM-116 implementation requirements

## R1 — Canonical ownership

Every P4 artifact class must have exactly one canonical owner and storage root.

## R2 — Exact provenance

Every generated artifact must resolve to exact source repository/ref/SHA, tool package/source commit, schema version, owner root and generation time.

## R3 — Fail-closed concurrency

Owner-root collisions, scope-hash mismatch, checkpoint revision mismatch, stale lease/fencing and duplicate idempotency keys must reject mutation without silent overwrite or merge.

## R4 — Compatibility

Submodule, power-dist, immutable-release and offline-zip modes must preserve backward-compatible fallback behavior. Missing boilerplate and BMAD ready-unpublished must remain explicit states.

## R5 — Authority separation

GWC gate artifacts and exact GitHub/CI evidence are authoritative for delivery; Jira owns roadmap/status; Notion and Slack are projections.
