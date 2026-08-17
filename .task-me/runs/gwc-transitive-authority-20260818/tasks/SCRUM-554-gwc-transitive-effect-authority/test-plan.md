# Test plan

## Planned focused tests
- `tests/test_gate_action_transitive_authority.py`
- `tests/test_gate_action_evidence_identity.py`
- `tests/test_gate_action_capability_compatibility.py`


## Required scenarios
1. Missing materialization/effect evidence fails closed.
2. Authorized direct action + unauthorized deterministic mutating child is blocked before execution.
3. Safe read-only deterministic child does not spuriously escalate authority.
4. Cross-repository mutating child without independent authority is blocked.
5. Correct PR-head evidence cannot satisfy a merge-SHA/post-merge node.
6. Same replay identity is equivalent; semantic drift under same identity is rejected.
7. Exact-base/head drift invalidates stale evidence.
8. Existing valid direct-action flows remain compatible when transitive closure is safe.

## CI discipline
After every pushed implementation/spec head, check CI for that exact SHA. If non-terminal, remain in-session, sleep 60 seconds, and re-read the exact SHA until terminal.
