## SCRUM-205: runtime_checkpoint.resume-token-validation M2 → M5_REPLAY_SAFE

**Task:** SCRUM-205
**Node:** `runtime_checkpoint.resume-token-validation`
**Maturity:** M2 → M5_REPLAY_SAFE
**Authority boundary:** G2_EXECUTION
**Family:** runtime_checkpoint

### Summary

Advanced `runtime_checkpoint.resume-token-validation` from thin metadata (M2) to
full replay-safe maturity (M5). The node now validates resume tokens and current
resume conditions before allowing interrupted G2 execution to continue.

### Changes

- Added `tools/node_architect/resume_token_validation.py` with:
  - Token integrity, expiry, task/run/node/gate/scope binding validation
  - Checkpoint digest, approval reference, lease/fencing token, repo base/head compatibility
  - Explicit route decisions: `RESUME`, `REAPPROVAL_REQUIRED`, `RECONCILE_REQUIRED`, `STOP_FAIL_CLOSED`
  - `authority_granted` is always `false` — token validity never creates gate PASS or merge/deploy authority
- Updated `core/node-architect/node-catalog/runtime_checkpoint/resume-token-validation.node.json`
  to M5 contract with routes, failure codes, implementation/test refs, and authority invariant
- Added `tests/test_resume_token_validation.py` covering:
  - Valid resume
  - Token expiry
  - Token tamper (invalid expiry format)
  - Missing token
  - Task mismatch
  - Scope mismatch (empty files_write)
  - Base drift
  - Head drift
  - Missing checkpoint
  - Stale approval
  - Checkpoint ID mismatch
  - Gate mismatch
  - Replay reuse outside policy
  - Authority never granted
  - Deterministic route decisions
  - RouteDecision serialization

### Authority boundary

- Node instructions and route decisions never grant G2/G3/G4/G5/G6 authority
- `authority_granted` is always `false`
- Token validation is execution-plane only; authority comes solely from validated
  gate artifacts and exact human approval where required