# SCRUM-368 Delivery Evidence

**Task:** SCRUM-368 · `failure_recovery.duplicate-agent-fencing`
**Run:** `SCRUM-288-NA81-20260811-R4`
**Parent Authority:** `AR-SCRUM288-20260811-R4` (materialized by `github-actions[bot]` on issue #232, comment `5251551984`)
**Classification:** `VERIFIED_REUSE`
**Delivered on SHA:** `aeb5cc23080c06cfeb633124aa56d0f6e4cccde3` (pre-prod base at worktree checkout)

---

## Requirement → Code → Test Evidence Map

### 1. Two-agent race / duplicate detection

| Requirement | Evidence |
|---|---|
| Concurrent/duplicate agents on same task/run → deny stale/duplicate actor | `tools/node_architect/cas_write_guard.py` lines 253–260 (`LEASE_OWNER_MISMATCH`), reason `STALE_OR_DUPLICATE_AGENT` |
| Fencing token mismatch → deny even when revision matches | lines 270–277 (`FENCING_MISMATCH`) |

**Test:** `tests/test_duplicate_agent_fencing_na81.py`
- `test_two_agent_race_stale_owner_denied` — different lease_owner → LEASE_OWNER_MISMATCH
- `test_stale_fence_denied_even_when_revision_matches` — wrong fencing_token → FENCING_MISMATCH

### 2. Current-holder verification

| Requirement | Evidence |
|---|---|
| Valid lease/fence holder may perform protected effect | lines 316–320 (`ALLOW_WRITE` when all bindings match) |

**Test:**
- `test_valid_current_holder_allows_write` — matching state → ALLOW_WRITE, next_revision=4

### 3. Deterministic readback + duplicate passive replay

| Requirement | Evidence |
|---|---|
| Same idempotency key already committed → return bound effect, no double write | lines 280–297 (`DUPLICATE_EFFECT_REPLAYED`) |
| Rejection returns `latest_observed_state` for readback | lines 90–95 (`_decision` includes `latest_state`) |

**Test:**
- `test_duplicate_passive_replay_returns_committed_effect` — DUPLICATE_EFFECT_REPLAYED + RESUME
- `test_split_brain_rejection_via_cas_mismatch` — second agent sees advanced revision → CAS_MISMATCH + REPAIR

### 4. Takeover after expiry / reconciliation

| Requirement | Evidence |
|---|---|
| Expired lease routes to reapproval | lines 299–306 (`LEASE_EXPIRED` → REAPPROVAL_REQUIRED) |

**Test:**
- `test_takeover_after_expiry_routes_to_reapproval` — observed_at >= lease_expires_at → LEASE_EXPIRED

### 5. Unknown effect / invalid input

| Requirement | Evidence |
|---|---|
| Malformed/missing input → INVALID_INPUT + STOP_BLOCKED | lines 183–228 (`_decision` with `INVALID_INPUT`) |

**Test:**
- `test_unknown_effect_invalid_input_fails_closed` — minimal dict → INVALID_INPUT/STOP_BLOCKED

### 6. Family invariants

| Invariant | Evidence |
|---|---|
| `ONLY_CURRENT_FENCE_HOLDER_MAY_EFFECT` | LEASE_OWNER_MISMATCH + FENCING_MISMATCH reject non-holders |
| `NO_SPLIT_BRAIN_SUCCESS` | CAS_MISMATCH prevents second writer after first advances revision; `persist_checkpoint` serializes commits |
| `RECOVERY_MUST_NOT_EXPAND_SCOPE_OR_AUTHORITY` | `auto_retry_allowed=False`; `merge_authority_granted=False` in all outcomes |

**Test:**
- `test_result_schema_accepts_all_outcomes` — schema conformance

---

## Verification Commands

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-368
# tests WITHOUT PYTHONPATH (SCRUM-323 import fix)
python -m unittest discover -s tests -p "test_duplicate_agent_fencing_na81.py"
# family validator
python3 tools/node_architect/validate_node_catalog_failure_recovery.py
```

## No code changes

No modification was made to `tools/node_architect/cas_write_guard.py`. Existing SCRUM-208 M5 tests (`tests/test_cas_write_guard.py`) remain green. SCRUM-368 NA81 tests (`tests/test_duplicate_agent_fencing_na81.py`) validate current-task requirement→code→test mapping on the exact accepted SHA `aeb5cc23`.
