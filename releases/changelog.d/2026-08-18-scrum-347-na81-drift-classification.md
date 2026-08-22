feat(gwc): SCRUM-347 NA81-F6 projection-drift multi-target classification

Implement the missing SCRUM-347 (NA81-F6-N05) drift-classification behavior
on top of the existing sync_projection drift node. The SCRUM-224 M4
`detect_projection_drift` only performs a single-projection field diff
(READY / PROJECTION_DRIFT_NONE vs BLOCKED / PROJECTION_DRIFT_DETECTED); it
lacked the SCRUM-347 taxonomy and per-target readback handling.

New behavior (DELTA_REQUIRED, backward-compatible — `detect_projection_drift`
is unchanged):

- `classify_projection_drift_na81(...)` compares the authoritative canonical
  source revision/digest against each projection target's readback and
  classifies NO_DRIFT / MATERIAL_DRIFT / CONFLICT / UNAVAILABLE_READBACK /
  STALE_READBACK.
- Stale / out-of-order readback detection: a readback whose `revision` differs
  from the canonical source `revision` is classified STALE_READBACK rather than
  silently treated as drift.
- Conflicting target state: when two or more fresh targets disagree on
  readback content, the aggregate classification is promoted to CONFLICT.
- Deterministic, order-independent `decision_digest`; read-only; every
  authority field fixed to false; canonical state is never inferred from a
  projection (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH); a readback failure
  never back-writes or mutates canonical outcome
  (PROJECTION_FAILURE_DOES_NOT_MUTATE_CANONICAL_OUTCOME).

New files:
- tests/test_projection_drift_detection_na81.py (13 NA81 classification tests)

Updated files:
- tools/node_architect/projection_drift_detection.py (classify_projection_drift_na81)

All authority fields are fixed to false; read_only_projection is fixed to
true. No connector call, network request, filesystem mutation, Jira
transition, approval, merge, deployment, release, or production operation.

Related: SCRUM-347 (#282), Epic SCRUM-288, Family SCRUM-294. Predecessors
SCRUM-343/344/345; consumer SCRUM-348.
