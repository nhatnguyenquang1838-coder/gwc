# SCRUM-190 — Tasks (Task Me plan)

- [ ] SUB-TASK-1 — Author `schemas/gate-transition-decision.schema.json` as a fully closed schema
      with the five-value outcome enum, binding blocks, and the next-node/reason-code contract.
- [ ] SUB-TASK-2 — Implement `tools/node_architect/gate_transition_decision.py` as a pure,
      replay-safe evaluator that resolves the next node from
      `core/task-lifecycle/gate-transition-map.yaml`, fails closed, and never performs a transition.
- [ ] SUB-TASK-3 — Add `tests/test_gate_authority_gate_transition_decision_m5.py` covering every
      outcome, precedence ordering, map-driven resolution, refusal paths, the no-transition
      invariant, and checkpoint/replay; run the focused module and review the full diff.

Execution order: SUB-TASK-1 → SUB-TASK-2 → SUB-TASK-3.

Validation: focused pytest module plus existing gate-authority regressions; complete local diff
review confined to the three approved implementation files and the SCRUM-190 evidence workspace.
