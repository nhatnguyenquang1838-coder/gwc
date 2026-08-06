feat(gwc): add projection-reconcile-readback runtime for SCRUM-225

Implement the M4 deterministic reconcile-readback evaluator for the
sync_projection family. It consumes the shared closed envelope, B1
decisions, the SCRUM-224 drift decision, a B2 external projection, and
a prior projection readback. An identical readback yields READY with
PROJECTION_CURRENT (NOOP); divergence, missing prior state, blocked
drift, or invalid input yields BLOCKED with stable reason codes and
sorted divergence_fields.

New files:
- schemas/projection-reconcile-readback.schema.json
- tools/node_architect/projection_reconcile_readback.py
- tests/test_reconcile_readback_m4_batch_b3.py (9 behavior tests)

Updated files:
- tools/node_architect/validate_node_catalog_sync_projection.py
- core/node-architect/node-catalog/sync_projection/README.md

All authority fields are fixed to false; read_only_projection is fixed
to true. No connector call, network request, filesystem mutation, Jira
transition, approval, merge, deployment, release, or production operation.

Tests:
- B3 reconcile-readback: 9/9 PASS
- B1 regression: 47/47 PASS
- Family validator: 12/12 PASS

Related: SCRUM-171 (sync_projection maturity F6).
