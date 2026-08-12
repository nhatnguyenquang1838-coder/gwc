# SCRUM-322 · Delivery Evidence (NA81, VERIFIED_REUSE)

- **Task:** SCRUM-322 — `repo_delivery.ci-failure-repair` · GitHub #257 · Family SCRUM-291 · Epic SCRUM-288
- **Pre-prod base SHA:** `b3480ddffcae74ba8428dde914244fca810b5be3`
- **Parent authority:** `AR-SCRUM288-20260811-R4` (issue #232, `github-actions[bot]`)
- **Classification:** VERIFIED_REUSE — implementation + tests already merged to `pre-prod`;
  this delivery adds the *current-task* requirement→code→test proof map and pins the
  current SCRUM-322 brief with `_na81.py` tests. No implementation delta was required
  (SCRUM-315 rule applied: existing code was read against the CURRENT brief, not assumed done).
- **Authority boundary:** g2_required (G2_EXECUTION + G3_PR). No merge/deploy/G4/G6.

## Current brief → code → test map (exact SHA b3480ddf)

| # | Current SCRUM-322 requirement (AC/EARS) | Code location (`tools/node_architect/ci_failure_repair.py`) | Test proof |
|---|---|---|---|
| 1 | Classify terminal exact-head CI failures into REPAIR_REPOSITORY | `classify_ci_failure` → `_classify_failure` (repo-fixable + external pattern sets) | `test_ci_failure_repair.py::test_repo_fixable_import`, `test_external_timeout`, `test_ci_failure_repair_na81.py::test_repo_fixable_inside_scope` |
| 2 | Permit only smallest repository-fixable repair inside approved scope | `decided_at`/scope branch: `if not approved_file_scope: decision="EVIDENCE_INVALID"; reason_code="CI_REPAIR_SCOPE_MISSING"` | `test_ci_failure_repair.py::test_evidence_invalid_when_scope_missing`, `test_ci_failure_repair_na81.py::test_missing_approved_scope_blocked` |
| 3 | External/unknown/out-of-scope/authority-lacking → typed blocker (fail closed) | `_EXTERNAL_PATTERNS` + `if ext_hits and not repo_hits: return "EXTERNAL_BLOCKED"`; else `EVIDENCE_INVALID` | `test_external_502`, `test_unknown_fails_closed`, `test_ci_failure_repair_na81.py::test_external_failure_blocked_typed`, `::test_unknown_failure_fails_closed` |
| 4 | Every repair creates a new head; invalidates prior CI/review evidence | `invalidate_prior_head_evidence = decision == "REPAIR_REPOSITORY"` | `test_ci_failure_repair.py::test_repair_repository_decision`, `test_ci_failure_repair_na81.py::test_new_head_invalidates_prior_evidence` |
| 5 | Repair does not expand scope or merge authority | `execution_performed=False` always; `remediation_scope="bounded-pr:..."` never contains merge | `test_ci_failure_repair.py::test_execution_performed_is_always_false`, `::test_decision_never_grants_merge_authority`, `test_ci_failure_repair_na81.py::test_no_merge_authority_ever`, `::test_classification_performs_no_execution` |
| 6 | Replay / idempotency conflict detection | `replay_status` (IDEMPOTENT / CONFLICT) from `prior_escalation` key match | `test_replay_idempotent`, `test_replay_conflict`, `test_ci_failure_repair_na81.py::test_replay_conflict_detected`, `::test_replay_idempotent_for_new_key` |
| 7 | Exact-head binding (head_sha must be 40-hex) | `re.fullmatch(r"[0-9a-f]{40}", head_sha, re.I)` raises `ValueError` | `test_ci_failure_repair.py::test_invalid_head_sha_rejected` |
| 8 | Historical SCRUM-199 is evidence only (no auto-close) | function only classifies + returns artifact; never mutates repo / transitions Jira | `test_ci_failure_repair_na81.py::test_classification_performs_no_execution` |

## Verification commands (run from repo root, no PYTHONPATH — matches CI)

```
python -m unittest tests.test_ci_failure_repair tests.test_ci_failure_repair_na81 -v
python tools/node_architect/validate_node_catalog_repo_delivery.py
```

## Delivered artifacts (this PR)
- `tests/test_ci_failure_repair_na81.py` — current-task proof tests pinning the SCRUM-322 brief.
- `.gwc/tasks/SCRUM-322/DELIVERY_EVIDENCE.md` — this map.
- (Implementation already on `pre-prod`; no code delta required.)
