feat(gwc): add projection-failure-routing runtime for SCRUM-226

Implement the M4 deterministic failure-routing evaluator for the
sync_projection family. It consumes the shared closed envelope, B1
decisions, the SCRUM-224 drift decision, and the SCRUM-225 reconcile
decision, then classifies the projection outcome into RETRYABLE,
HARD_DENIED, STALE_EVIDENCE, or AUTHORITY_CONFLICT. Routing is pure
classification; no connector call, network request, filesystem mutation,
Jira transition, approval, merge, deployment, release, or production operation.

New files:
- schemas/projection-failure-routing.schema.json
- tools/node_architect/projection_failure_routing.py
- tests/test_failure_routing_m4_batch_b3.py (9 behavior tests)

Updated files:
- tools/node_architect/validate_node_catalog_sync_projection.py
- core/node-architect/node-catalog/sync_projection/README.md

All authority fields are fixed to false; read_only_projection is fixed
to true.

Tests:
- B3 failure-routing: 9/9 PASS
- B1 regression: 47/47 PASS
- Family validator: 12/12 PASS

Related: SCRUM-171 (sync_projection maturity F6).
