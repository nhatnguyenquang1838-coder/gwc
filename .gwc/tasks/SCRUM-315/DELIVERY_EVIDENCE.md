# SCRUM-315 — Current-Task Delivery Evidence Map (NA81)

Exact SHA: `cf0231cd464c0fb309ccaf9c38527edae4bd19d2` (origin/pre-prod HEAD at delivery)
Parent authority: `AR-SCRUM288-20260811-R4` (github-actions[bot] receipt 5251551984)
Route: `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`

## Classification: DELTA_REQUIRED (NOT VERIFIED_REUSE)

Historical SCRUM-192 (M5) provided `escalate_blocked_action` with only a
checkpoint-before-wait gate (decisions WAIT / RESOLVE_MINIMAL). The current NA81
brief (SCRUM-315 / GitHub #250) requires deterministic BLOCKED / HUMAN_REQUIRED
outcomes for unauthorized / stale / expired / unsupported / unknown-evidence
actions, fail-closed on missing evidence, full escalation-class routing, zero
protected side effects, no approval manufacture, no scope broadening, and replay
determinism. The M5 code did NOT satisfy these; hence a real implementation delta
exists and a no-op PR would have been wrong.

## Requirement -> Code -> Test mapping (exact SHA)

| Requirement (SCRUM-315 brief) | Code | Test |
|---|---|---|
| Convert unauthorized action -> HUMAN_REQUIRED | `authority_check=UNAUTHORIZED` -> decision HUMAN_REQUIRED, ESC_REQUEST_HUMAN_INPUT | test_unauthorized_human_required |
| Convert unsupported action -> BLOCKED terminal | `AUTH_UNSUPPORTED` -> DECISION_BLOCKED, ESC_TERMINAL_STOP | test_unsupported_terminal_stop |
| Convert stale (base/head drift) -> BLOCKED recapture | `AUTH_STALE` -> DECISION_BLOCKED, ESC_RECAPTURE_BASE_OR_HEAD | test_stale_recapture |
| Convert expired authority -> HUMAN_REQUIRED revalidate | `AUTH_EXPIRED` -> DECISION_HUMAN_REQUIRED, ESC_REVALIDATE_SCOPE | test_expired_revalidate_scope |
| Unknown/unavailable evidence -> fail closed | `evidence_available=False` -> DECISION_BLOCKED, ESC_REMEDIATE_EVIDENCE | test_unknown_evidence_fails_closed, test_unknown_authority_fails_closed |
| Zero protected side effects | `execution_performed` always False | test_execution_never_performed |
| Never manufacture approval / broaden scope | remediation_scope null on HUMAN_REQUIRED; `minimal-exact:<action>` only | test_no_approval_manufactured, test_no_scope_broadening |
| Checkpoint-before-wait | `checkpoint_done` gate -> WAIT (ESC_WAIT_FOR_READBACK) / RESOLVE_MINIMAL (ESC_WAIT_FOR_CI) | test_wait_when_checkpoint_pending, test_resolve_minimal_when_checkpoint_done |
| Replay determinism + conflict | digest over canonical inputs; IDEMPOTENT/CONFLICT | test_replay_idempotent, test_replay_conflict, test_deterministic_digest |
| Input validation | reject unknown action / authority | test_invalid_action_rejected, test_invalid_authority_rejected |

## Files changed (this delivery)
- `tools/node_architect/blocked_action_escalation.py` (extended: authority_check + evidence_available + escalation_class routing)
- `schemas/blocked-action-escalation.schema.json` (decision enum + escalation_class + authority_check/evidence_available)
- `tests/test_gate_authority_blocked_action_escalation_na81.py` (NEW, 18 tests — current-task mapping)
- `tests/test_gate_authority_blocked_action_escalation_m5.py` (unchanged; backward-compat via default params)

## Verification
- `PYTHONPATH=. python3 -m unittest tests.test_gate_authority_blocked_action_escalation_na81` -> 18/18 PASS
- `PYTHONPATH=. python3 -m unittest tests.test_gate_authority_blocked_action_escalation_m5` -> 10/10 PASS (backward compat)
- `PYTHONPATH=. python3 tools/node_architect/validate_node_catalog_gate_authority.py` -> all_present=true, errors=[]
- Family flow + node catalog tests: 8/8 PASS

## Dependency safety
Predecessor SCRUM-311 verified by live Jira status Done (re-checked this tick). SCRUM-315 was
prematurely marked Done earlier in the same tick based only on historical code presence; that
auto-close was reverted (comment on SCRUM-315) because it violated the brief's DONE_UNVERIFIED rule.
This evidence map is the required current-task proof; consumers may unlock after exact-merge-SHA G5.
