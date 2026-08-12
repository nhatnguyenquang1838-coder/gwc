# SCRUM-327 Delivery Evidence

## Current-task requirement → code → test evidence map

| # | Requirement (brief / instruction) | Code location | Test |
|---|-----------------------------------|---------------|------|
| 1 | Render scoped resume token binding exact checkpoint, task/run, head, scope, expiry | `tools/node_architect/generate_resume_token.py:55` `generate_resume_token` | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_valid_token_binds_context_and_validates_schema` |
| 2 | Invalid checkpoint must not yield a usable token (checkpoint None / non-mapping) | `tools/node_architect/generate_resume_token.py:72` `RESUME_TOKEN_CHECKPOINT_INVALID` guard | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_none_checkpoint_fails_closed` |
| 3 | Wrong head / scope / run is detectable via faithful binding + token digest mismatch | `tools/node_architect/generate_resume_token.py:103` `binding` dict includes head_sha/scope_hash | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_wrong_head_scope_run_is_detectable` |
| 4 | Expiry must follow issue time | `tools/node_architect/generate_resume_token.py:92` `expires <= issued` guard | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_expiry_must_follow_issue_time` |
| 5 | Tamper is detected via token_digest | `tools/node_architect/generate_resume_token.py:124` `token["token_digest"] = digest(token)` | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_tamper_is_detected` |
| 6 | Replay equivalence (deterministic) | `tools/node_architect/generate_resume_token.py:24` `canonical_json` + `digest` | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_generation_is_deterministic_for_same_context` |
| 7 | No authority expansion; generation grants no authority | `tools/node_architect/generate_resume_token.py:118` `authority_* = False` + gate guard | `tests/test_resume_token_generation_na81.py::SCRUM327NA81Tests::test_no_authority_expansion` |

## Verification commands

```bash
cd /Users/mac/prj/gwc-wt-SCRUM-327
python3 -m unittest discover -s tests -p "test_resume_token*.py"
PYTHONPATH=. python3 tools/node_architect/validate_node_catalog_gate_authority.py
```

## Artifacts

- Base ref: `pre-prod`
- Approved base SHA (R4): `4ddc8a01b1d6d957ea70bef621646354897b55ef`
- Working branch: `auto/SCRUM-327-na81-20260810`
- Head SHA after commit: `<filled after push>`
- PR: `<filled after gh pr create>`
