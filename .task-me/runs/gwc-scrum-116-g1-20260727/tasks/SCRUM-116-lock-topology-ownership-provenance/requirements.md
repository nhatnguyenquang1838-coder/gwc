# SCRUM-116 requirements handoff

## R1 — Canonical ownership

Every P4 artifact type resolves to exactly one owner and storage root. Tool source, package distribution, target-owned generated output, gate state and external projections must not share authority.

## R2 — Provenance

Every generated artifact resolves through artifact ID, parent artifact ID, source repository/ref/SHA, tool package/source commit, schema version, owner root and generated time.

## R3 — Mutation safety

Parallel execution fails closed on stale lease/fencing token, checkpoint revision mismatch, scope hash mismatch, duplicate idempotency key or owner-root collision.

## R4 — Compatibility

Submodule, power-dist, immutable release and offline ZIP inputs remain supported as explicit modes; absent DW-SuperApps boilerplate and BMAD `ready-unpublished` remain explicit states.

## R5 — Authority separation

GWC artifacts and exact GitHub/CI evidence are authoritative. Jira, Notion and Slack are non-authoritative projections/communication.
