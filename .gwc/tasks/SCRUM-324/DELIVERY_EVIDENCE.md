# SCRUM-324 DELIVERY_EVIDENCE

## Requirement → Code → Test Evidence Map (exact head `d6fac7c9`)

### Current brief (Jira SCRUM-324 + GitHub #259)

| Requirement (from Jira brief §AGENT MUST DO / node descriptor) | Evidence (code + test on exact SHA `d6fac7c9`) |
|---|---|
| Aggregate PR, exact-head CI, review/evidence quality, scope/authority blockers into one deterministic readiness state | `tools/node_architect/validate_node_catalog_repo_delivery.py::decide_pr_blocker_check()` |
| Missing/stale/mixed-head/contradictory/unavailable evidence → `BLOCKED`, `PENDING_RETRY`, or `HUMAN_REQUIRED` | Tests: `test_stale_check_returns_blocked`, `test_head_sha_mismatch_returns_blocked`, `test_ci_pending_returns_pending_retry`, `test_unsupported_reviewer_returns_human_required` |
| CI non-terminal (in_progress / queued / missing checks) → `PENDING_RETRY` | `decide_pr_blocker_check` maps non-terminal checks to `wait()` bucket → `PENDING_RETRY` |
| Unsupported reviewer (empty author / no reviews) → `HUMAN_REQUIRED` | `decide_pr_blocker_check` maps empty-reviewer to `human()` bucket → `HUMAN_REQUIRED` |
| Readiness never grants merge authority | `_no_higher_authority()` included in return; `test_merge_authority_never_granted` covers all four outcomes |
| Idempotent / deterministic digest | `test_deterministic_digest`, `test_digest_format` |

### Verification commands (exact)

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-324
python3 tools/node_architect/validate_node_catalog_repo_delivery.py
PYTHONPATH=tools python3 tests/test_repo_delivery_pr_blocker_check_na81.py -v
python3 -m unittest discover -s tests -p 'test_repo_delivery_pr_blocker_check_na81.py'
```

### Classification

- **DELTA_REQUIRED** — Existing `decide_pr_blocker_check` only produced `CLEAR|BLOCKED`. NA81 brief explicitly requires `PENDING_RETRY` and `HUMAN_REQUIRED` outcomes; historical SCRUM-201 tests are retained as reuse evidence only and do not satisfy the current brief.
