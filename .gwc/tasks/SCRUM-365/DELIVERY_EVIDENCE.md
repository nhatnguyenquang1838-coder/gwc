# SCRUM-365 · NA81 Delivery Evidence — failure_recovery.cas-mismatch-recovery

- **Jira:** SCRUM-365 · **GitHub:** #300 · **Epic:** SCRUM-288 · **Family:** SCRUM-296 (failure_recovery)
- **Parent authority:** AR-SCRUM288-20260811-R4 (run `SCRUM-288-NA81-20260811-R4`, issue #232)
- **Classification:** DELTA_REQUIRED (brief explicitly forbids no-op / auto-close; historical SCRUM-242 is reuse evidence only)
- **Predecessors verified Done:** SCRUM-331/#266 + SCRUM-332/#267
- **Branch:** `auto/SCRUM-365-na81-20260810` (manifest-fixed date)
- **Base SHA (pre-prod):** `a28b8eb6035d2545d619b76f460651acc6332e5d`
- **Head SHA (PR):** `b5e9ef9b43fabfb28ea56327ed943c29c4048e28`

## Requirement → Code → Test map (current-task delivery proof)

| NA81 requirement (SCRUM-365 brief) | Code (`tools/node_architect/cas_mismatch_recovery.py`) | Test (`tests/test_cas_mismatch_recovery_na81.py`) |
|---|---|---|
| `CAS_MISMATCH => AUTHORITATIVE_REREAD_BEFORE_NEXT_WRITE` | `reload_status != "VERIFIED" -> RELOAD`; emitted `authoritative_reread_required` flag (true for every non-`NO_MISMATCH` outcome) | `test_conflicting_state_requires_reload`, `test_newer_compatible_state_retries_after_reload` |
| Stale actor cannot overwrite newer state (fence) | `stale_writer` check (actor_id / fence_token mismatch) -> `STALE_WRITER_DENIED`, takes precedence over revision logic | `test_stale_actor_denied`, `test_stale_fence_denied`, `test_stale_writer_precedence_over_matching_revision` |
| Deterministic retry / replan / block routing (no blind retry) | `plan_status == "STALE" -> REPLAN`; `RETRY_AFTER_RELOAD` under budget; `FAIL` on budget exhaust; `HUMAN_REQUIRED`; `RECONCILE` | `test_plan_stale_replans`, `test_repeated_mismatch_exhausts_budget`, `test_regressed_revision_requires_human`, `test_pending_action_reconciles` |
| `RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY` | `overwrite_allowed=False` and `blind_retry_allowed=False` invariant across all outcomes | `test_no_write_or_blind_retry_under_any_routing` |
| Concurrency replay equivalence | `is_replay_equivalent` ignores `observed_at`/`decision_digest` but not actor | `test_concurrency_replay_equivalent` |
| Explicit `NO_MISMATCH` when revisions agree | `observed_revision == expected_revision -> NO_MISMATCH`; `authoritative_reread_required=False` | `test_no_mismatch_is_explicit` |
| No auto-close: historical SCRUM-242 ≠ current delivery | New NA81 test + this evidence map; old `test_cas_mismatch_recovery.py` (SCRUM-242) kept green | `tests.test_cas_mismatch_recovery` (6 tests, unchanged expectations) |

## Schema extension (backward compatible)

`schemas/cas-mismatch-recovery-decision.schema.json` gained two new `outcome` enum
values (`REPLAN`, `STALE_WRITER_DENIED`) and optional properties (`actor_id`,
`expected_actor_id`, `fence_token`, `expected_fence_token`, `plan_status`,
`authoritative_reread_required`, `stale_writer_denied`). `additionalProperties`
stays `false`; no required field was added, so prior decisions still validate.

## Verification commands (run from repo root, no PYTHONPATH)

```bash
python3 -m unittest tests.test_cas_mismatch_recovery tests.test_cas_mismatch_recovery_na81
python3 tools/node_architect/validate_node_catalog_failure_recovery.py
```

Both PASS locally (18 tests; family validator PASS).
