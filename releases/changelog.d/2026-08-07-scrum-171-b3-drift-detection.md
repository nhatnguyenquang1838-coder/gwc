feat(gwc): add projection-drift-detection runtime for SCRUM-224

Implement the M4 deterministic drift-detection runtime for the
sync_projection family. The new evaluator consumes the shared closed
envelope, the three B1 decisions (source-authority, evidence-linkset,
privacy-boundary), a B2-rendered external projection, and a canonical
state snapshot, then compares the projection's canonical_state against
the snapshot field-by-field. Divergence yields BLOCKED with sorted
drift_fields and an order-independent canonical_state_digest; a clean
comparison yields READY with PROJECTION_DRIFT_NONE.

New files:
- schemas/projection-drift-decision.schema.json (closed result contract)
- tools/node_architect/projection_drift_detection.py (detect_projection_drift)
- tests/test_drift_detection_m4_batch_b3.py (11 behavior + fails-closed tests)

Updated files:
- tools/node_architect/validate_node_catalog_sync_projection.py (drift lane)
- core/node-architect/node-catalog/sync_projection/README.md (B3 contract)

All authority fields are fixed to false; read_only_projection is fixed
to true. No connector call, network request, filesystem mutation, Jira
transition, approval, merge, deployment, release, or production operation.

Tests:
- B3 drift-detection: 11/11 PASS
- B1 regression: 47/47 PASS
- Family validator: 12/12 PASS

Related: SCRUM-171 (sync_projection maturity F6).
