# Requirements

## Objective
Define the UA host-mode contract so every structural/domain graph snapshot is fresh, version-bound, reproducible and read-only with respect to product source and canonical GWC state.

## Acceptance criteria
- Bind target repository, ref, SHA and UA package/source commit.
- Reject stale or mismatched snapshots; no silent reuse.
- Write generated outputs only under target-owned `.ua/**`.
- Return typed statuses for COMPLETE, REFRESH_REQUIRED, INVALID_INPUT and TOOL_UNAVAILABLE.
- Preserve SCRUM-116 provenance, owner-root, scope, checkpoint, lease/fencing and idempotency guards.
