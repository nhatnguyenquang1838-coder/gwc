# SCRUM-360 — DELIVERY EVIDENCE

Node: `package_export.export-failure-routing` (F7)
GitHub: #295 | Jira: SCRUM-360 | Epic: SCRUM-288
Classification: **VERIFIED_REUSE** (existing code+tests on exact HEAD already satisfy current NA81 brief)

---

## Requirement → Code → Test Map

| Brief Requirement (NA81) | Evidence Code | Evidence Test |
|---|---|---|
| Classify manifest/schema/path/build/hash/smoke failures | `DECISION_TABLE` in `tools/node_architect/package_export/export_failure_routing.py` covers SCHEMA_*, MANIFEST_*, SOURCE_*, TARGET_*, TREE_*, HASH_*, SMOKE_* reason namespaces | `TestEveryUpstreamReason.test_every_reason_routes` (17/17 pass) |
| Route bounded remediation (repair/rebuild/re-read/bounded retry/human required/fail closed) | 6 `ROUTE_*` constants + `Route` enum; `route_failure()` returns exactly one | Same test + `TestFamilyGoldenFlows` |
| Unknown/unavailable/contradictory outcomes never PASS | `REASON_FAILURE_UNMAPPED` → `ROUTE_FAIL_CLOSED` | `test_unknown_reason_fails_closed` |
| No publish/release/deploy authority inferred | `authority_authorized=False` on every `RouteDecision` | `test_no_route_grants_authority` |
| Bounded retry requires reconciled readback | `checkpoint_reconciled` gate in `RoutingContext` | `test_retry_requires_reconciled_readback` |
| Retry exhausted → fail closed | `retry_count >= max_retry` + deadline guard | `test_retry_exhausted`, `test_retry_deadline_passed` |
| Conflicting replay → human required | `checkpoint_interrupted` + not reconciled → `REASON_REPLAY_CONFLICT` → `HUMAN_REQUIRED` | `test_interrupted_without_reconciliation_conflict` |
| Idempotent evidence = same digest, no duplicate effect | `compute_decision_digest` over canonical fields | `test_identical_evidence_same_digest` |

---

## Exact HEAD SHA

```
d6fac7c9d007dfd9b1e024c3994e4a3e1797481d
```
Pre-prod HEAD at materialization. Message: `SCRUM-309: gate_authority.approval-command-validation actor/target binding + maturity`

---

## Verification Commands (run on HEAD above)

```bash
python3 -m unittest tests.package_export.test_export_failure_routing
python3 tools/node_architect/validate_node_catalog_package_export.py
```

Results: 17 tests OK, family validator PASS.

---

## Delivery Proof

- `tests/package_export/test_export_failure_routing_na81.py` added as focused current-task proof
  (brief category coverage + unknown/fail-closed + no-authority + bounded-retry reconciliation)
- `.gwc/tasks/SCRUM-360/DELIVERY_EVIDENCE.md` is the requirement→code→test evidence map
- Standing G4 `AR-SCRUM288-20260811-R4` authorizes `auto/* -> pre-prod` merge
