# SCRUM-331 Delivery Evidence

**Task:** SCRUM-331 · `runtime_checkpoint.cas-write-guard`
**Run:** `SCRUM-288-NA81-20260811-R4`
**Parent Authority:** `AR-SCRUM288-20260811-R4` (materialized by `github-actions[bot]` on issue #232, comment `5251551984`)
**Classification:** `VERIFIED_REUSE`
**Delivered on SHA:** `c72d715d0d4dc0e52cad415108b09340f4393b64` (pre-prod base at worktree checkout)

---

## Requirement → Code → Test Evidence Map

### 1. Expected-version/fence guarded write

| Requirement | Evidence |
|---|---|
| `expected_revision` vs `observed_revision` CAS check; mismatch routes to REPAIR/readback | `tools/node_architect/cas_write_guard.py` lines 245–251 (`BASE_DRIFT`), 308–314 (`CAS_MISMATCH`) |
| `fencing_token` vs `observed_fencing_token` | lines 270–277 (`FENCING_MISMATCH`) |
| Write allowed only when all bindings match | lines 316–320 (`ALLOW_WRITE`) |

**Test:** `tests/test_cas_write_guard_na81.py`
- `test_successful_cas_allows_one_monotonic_write` — matching rev → ALLOW_WRITE, next_revision=4, auto_retry=False
- `test_stale_version_routes_to_repair` — rev mismatch → CAS_MISMATCH + REPAIR + latest_observed_state readback
- `test_stale_fence_rejects_even_when_revision_matches` — fence mismatch → FENCING_MISMATCH + ABORT_STALE_WORKER

### 2. Stale actor denied

| Requirement | Evidence |
|---|---|
| `lease_owner` mismatch → deny | lines 253–260 (`LEASE_OWNER_MISMATCH`) |
| `lease_token` mismatch → deny | lines 262–268 (`LEASE_STALE`) |

**Test:**
- `test_wrong_actor_owner_is_fenced` — LEASE_OWNER_MISMATCH + STALE_OR_DUPLICATE_AGENT
- `test_wrong_actor_scope_routes_to_reapproval` — SCOPE_MISMATCH → REAPPROVAL_REQUIRED

### 3. Concurrent race / duplicate effect replay

| Requirement | Evidence |
|---|---|
| Same idempotency key already committed → return bound effect, no double write | lines 280–297 (`DUPLICATE_EFFECT_REPLAYED`) |
| Fencing still checked on replay | lines 150–154 in existing tests (test_duplicate_effect_does_not_bypass_current_fencing_check) |

**Test:**
- `test_concurrent_race_duplicate_effect_replays` — DUPLICATE_EFFECT_REPLAYED + RESUME

### 4. Unknown / invalid write fails closed

| Requirement | Evidence |
|---|---|
| Malformed/missing input → INVALID_INPUT + STOP_BLOCKED | lines 183–228 (`_decision` with `INVALID_INPUT`) |

**Test:**
- `test_unknown_write_invalid_input_fails_closed` — minimal dict → INVALID_INPUT/STOP_BLOCKED

### 5. Readback + replay determinism

| Requirement | Evidence |
|---|---|
| Rejection returns `latest_observed_state` | lines 90–95 (`_decision` includes `latest_state`) |
| Equivalent replay yields same decision digest | `canonical_json` + `digest_payload` produce deterministic digests |

**Test:**
- `test_readback_returns_latest_observed_state_on_mismatch` — CAS_MISMATCH returns `{revision: 3, status: ready}`
- `test_replay_is_idempotent` — same observation → same outcome + same decision_digest

### 6. Schema conformance

| Requirement | Evidence |
|---|---|
| Decision output matches `cas-write-guard-result.schema.json` | `tests/test_cas_write_guard.py::test_result_schema_accepts_all_outcomes` (M5 green) + `tests/test_cas_write_guard_na81.py::test_result_schema_accepts_all_outcomes` |

---

## Verification Commands

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-331
# tests WITHOUT PYTHONPATH (SCRUM-323 import fix)
python -m unittest discover -s tests
# family validator
python3 tools/node_architect/validate_node_catalog_runtime_checkpoint.py
```

## No code changes

No modification was made to `tools/node_architect/cas_write_guard.py`. Existing SCRUM-208 M5 tests (`tests/test_cas_write_guard.py`) remain green. SCRUM-331 NA81 tests (`tests/test_cas_write_guard_na81.py`) validate current-task requirement→code→test mapping on the exact accepted SHA `c72d715d`.
