# Test plan

## Planned focused tests
- `tests/test_gate_action_transitive_authority.py`
- `tests/test_gate_action_evidence_identity.py`
- `tests/test_gate_action_capability_compatibility.py`

## Required scenarios
1. Missing/invalid effect-graph ref or digest fails closed when the action is trigger-capable or profile is unknown.
2. Authorized direct action + unauthorized deterministic mutating child is blocked.
3. Safe read-only/compute child does not spuriously escalate authority.
4. Cross-repository mutating child without independent repo authority is blocked.
5. Correct PR-head evidence cannot satisfy merge-SHA/post-merge evidence identity.
6. A successful historical workflow/check for a different SHA/event/gate is rejected as current authority evidence.
7. Conditional child: predicate `false` excludes only with bound evidence; `true` is reachable; `unknown` mutating child is treated as potentially reachable and authority-closed or blocked.
8. Retention/delete child maps to destructive capability and cannot be absorbed into ordinary release/publish.
9. Same replay identity is equivalent; effect-graph/policy/evidence drift under the same identity is rejected.
10. Legacy packet with trusted `NO_TRANSITIVE_MUTATION` profile remains compatible without an effect graph; trigger-capable/unknown legacy packet without graph fails `EFFECT_GRAPH_REQUIRED`.
11. Existing safe G0-G6 direct-action packets remain valid when their trusted action profile proves no unauthorized transitive mutation.
12. Capability registry, effect graph and lifecycle docs expose one consistent semantic source of truth.

## CI discipline
After every pushed implementation/spec head, check CI for that exact SHA. If non-terminal, remain in-session, sleep 60 seconds, and re-read the exact SHA until terminal.
