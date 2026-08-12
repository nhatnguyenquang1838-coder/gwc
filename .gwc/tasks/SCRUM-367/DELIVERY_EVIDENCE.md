# SCRUM-367 — DELIVERY_EVIDENCE

## Classification

DELTA_REQUIRED

## Branch / Head

- Branch: `auto/SCRUM-367-na81-20260810`
- Pre-prod base at push: `6e6984e3bb120a222b65c99767f2747aa9bd0464`

## Requirement → Code → Test evidence map

| Current AC (SCRUM-367 brief) | Code | Test |
|---|---|---|
| Stop all use of expired approval, never treat expiry as implicit renewal/grace/transitive authority | `decide_approval_expiry_recovery` — expired = now >= expires_at; continuation_allowed = False on expiry | `ExpiryBoundaryTests.test_at_boundary_is_expired`, `test_before_boundary_is_not_expired` |
| Stale scope/head blocks continuation | `scope_drifted = approval_scope_hash != current_scope_hash`; head change implies scope drift | `StaleScopeHeadTests.test_scope_hash_drift_blocks`, `test_head_change_implies_scope_drift` |
| Duplicate approval (replay) rejected | `replay_detected = replay_nonce in consumed_replay_nonces`; REJECT_REPLAY with wait/continuation False | `ReplayTests.test_duplicate_replay_nonce_rejected`, `test_fresh_nonce_not_replay` |
| Valid replacement approval continues | Not expired, not drifted, valid checkpoint + replay → CONTINUE with continuation_allowed True | `ValidReplacementTests.test_valid_approval_continues` |
| No replacement available / expired blocks | expired → REGENERATE_APPROVAL, regenerate_approval_required True, continuation_allowed False | `ValidReplacementTests.test_valid_replacement_after_expiry_requires_fresh_approval` |
| No transitive authority | stale_continuation_allowed = False always; expired → continuation_allowed = False; decision never grants authority | `NoTransitiveAuthorityTests.test_expired_approval_never_grants_continuation`, `test_decision_never_grants_authority` |
| Checkpoint preservation before wait | continuation_requested + missing checkpoint → CHECKPOINT_BEFORE_WAIT | `CheckpointEvidenceTests.test_missing_checkpoint_blocks_wait` |
| Checkpoint drift during wait regenerates | continuation_requested + mismatch → REGENERATE_APPROVAL, CHECKPOINT_DRIFTED_DURING_WAIT | `CheckpointEvidenceTests.test_checkpoint_mismatch_during_wait_regenerates` |
| Deterministic replay-safe digest | `attach_digest` + `replay_safe` ignoring observed_at/decision_digest | `ReplaySafeStabilityTests.test_identical_inputs_are_replay_safe`, `test_different_inputs_are_not_replay_safe` |

## Verification

- `PYTHONPATH=. python -m unittest tests.test_approval_expiry_recovery_na81` → 14 passed
- `PYTHONPATH=. python -m unittest tests.test_failure_recovery_m5_batch` → 16 passed (M5 compat)
- `python tools/node_architect/validate_node_catalog_failure_recovery.py` → PASS
- CI import path verified: `python3 -m unittest discover -s tests -p "test_approval_expiry_recovery_na81.py"` → 14 passed (repo root on path, no PYTHONPATH)

## Parent authority

`AR-SCRUM288-20260811-R4` (receipt comment 5251551984 on issue #232, github-actions[bot])
Allowed task SCRUM-367; working branch `auto/SCRUM-367-na81-20260810`; target `pre-prod` only.
