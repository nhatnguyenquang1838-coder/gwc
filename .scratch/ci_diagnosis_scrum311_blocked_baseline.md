# CI_DIAGNOSIS SCRUM-311 — BLOCKED_UNRELATED_BASELINE_VALIDATE

pr=439 | head=2d282c3cb482b46e522592dd4ca3439606b10082 | target=pre-prod (draft)
validate run=31601472176 job=94129686127 step="Run governance unit tests"

## Command (from CI log line 705)
python -m unittest discover -s tests -p "test_*.py"   # 1943 tests, FAILED (failures=34)

## Reproduction on clean origin/pre-prod e1808798 (delta ABSENT)
Same command -> FAILED (failures=34), 1934 tests (my na81 file absent).
=> failure is identical with and without SCRUM-311 delta. Causality: baseline rot.

## Failing tests (none touch SCRUM-311 files)
- 20 FAIL methods asserting text now missing from agents/chatgpt-agent/gwc-governed-base.md
  ("Composed Entrypoint" doc refactor): test_chat_connector_runtime_contract,
  test_gate_lifecycle_process_contract, test_g4_g5_evidence_workflow,
  test_g4_g5_evidence_structure, test_chatgpt_agent_runbook_continuation.
- 14 inline ERROR validators: releases/changelog.d (missing/missing-task fragment),
  contract "Reconcile before retry", schema "lease_required",
  scale_81_nodes_allowed, node_version_drift_pins_or_restarts,
  reference-nodes/scoped-write.node.json idempotency key.

## SCRUM-311 scope (3 files, delta only)
tools/node_architect/authority_boundary_check.py (+envelope_expires_at/stale_evidence/evidence_age_s + 2 reject codes)
schemas/authority-boundary-decision.schema.json (+2 optional fields)
tests/test_gate_authority_authority_boundary_check_na81.py (9 tests, GREEN locally)

## Gates that PASSED on head 2d282c3c
parent-authority-required=SUCCESS, contract-canary=SUCCESS,
autonomous-g4-evidence-required=SUCCESS, build=SUCCESS, parity=SUCCESS.
g4-authority=SKIPPED (merge-time only).

## Ruling compliance
- DO NOT merge PR #439.
- DO NOT transition SCRUM-311 Done / claim G5.
- DO NOT start SCRUM-314.
- DO NOT expand into cross-lane baseline repair (out of authority).
STATE: BLOCKED_UNRELATED_BASELINE_VALIDATE (proof bounded above). PR left draft/open.
