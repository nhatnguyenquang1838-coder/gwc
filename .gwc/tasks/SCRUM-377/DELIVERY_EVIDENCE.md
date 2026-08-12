# SCRUM-377 — DELIVERY_EVIDENCE

## Classification

DELTA_REQUIRED

## Branch / Head

- Branch: `auto/SCRUM-377-na81-20260810`
- Pre-prod base at push: `6e6984e3bb120a222b65c99767f2747aa9bd0464`

## Requirement → Code → Test evidence map

| Current AC (SCRUM-377 brief) | Code | Test |
|---|---|---|
| Deterministic non-authoritative rollout progress from verified canonical inventory + exact merge/G5 evidence | `decide_rollout_progress_projection` — computes progress only from provided `family_progress`, `gate_evidence`, `evidence_revision`, `expected_revision`; all authority fields fixed to False | `CleanProgressTests.test_all_complete_ready_for_audit_handoff` |
| UNKNOWN / BLOCKED / PENDING stay explicit | UNKNOWN gate status → `INVALID_GATE_EVIDENCE_INPUT` (BLOCKED); BLOCKED/PENDING gates → explicit projection status | `UnknownExplicitTests.test_unknown_gate_status_never_silently_counts`, `CleanProgressTests.test_blocked_gates_show_blocked`, `test_pending_gates_show_in_progress` |
| Unsafe Jira Done or historical impl never count as completed | Projection derives only from canonical `family_progress` completed_nodes; external Jira status never observed or counted | `UnknownExplicitTests.test_unsafe_jira_done_does_not_inflate_progress` |
| Missing G5 evidence blocks | Gate entry with invalid evidence_sha → `INVALID_GATE_EVIDENCE_INPUT`, projection_status BLOCKED | `MissingG5Tests.test_missing_g5_evidence_blocks` |
| Changed denominator blocks | total_nodes mismatch against expected_total_nodes → `TOTAL_NODE_COUNT_MISMATCH`, BLOCKED | `ChangedDenominatorTests.test_changed_denominator_blocks` |
| Stale projection blocks | evidence_revision != expected_revision → `EVIDENCE_REVISION_MISMATCH`, BLOCKED | `StaleProjectionTests.test_stale_evidence_revision_blocks` |
| Replay / deterministic revision + digest | Identical inputs → identical decision_digest + progress_percent; different inputs → different digest | `DeterministicRevisionDigestTests.test_identical_inputs_yield_stable_digest`, `test_different_inputs_yield_different_digest` |
| Never grants scale/merge/deployment/production authority | All authority fields fixed to False; read_only_projection = True | `DeterministicRevisionDigestTests.test_no_authority_granted_ever` |

## Verification

- `PYTHONPATH=. python -m unittest tests.test_rollout_progress_projection_na81` → 11 passed
- `PYTHONPATH=. python -m unittest tests.test_node_catalog_scale_control` → 8 passed (catalog compat)
- `python tools/node_architect/validate_node_catalog_scale_control.py` → PASS
- CI import path verified: `python3 -m unittest discover -s tests -p "test_rollout_progress_projection_na81.py"` → 11 passed (repo root on path, no PYTHONPATH)

## Parent authority

`AR-SCRUM288-20260811-R4` (receipt comment 5251551984 on issue #232, github-actions[bot])
Allowed task SCRUM-377; working branch `auto/SCRUM-377-na81-20260810`; target `pre-prod` only.
