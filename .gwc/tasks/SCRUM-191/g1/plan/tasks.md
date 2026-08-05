# SCRUM-191 — Tasks (Task Me plan)

- [ ] SUB-TASK-1 — Author `schemas/g2-execution-envelope.schema.json` as a fully closed schema with
      the lifecycle enum, F1/F2 binding blocks, and the mandatory later-gate exclusion set.
- [ ] SUB-TASK-2 — Implement `tools/node_architect/g2_execution_envelope_render.py` as a pure,
      deterministic renderer with fail-closed refusal codes and a replay digest.
- [ ] SUB-TASK-3 — Add `tests/test_gate_authority_g2_execution_envelope_render_m5.py` covering
      determinism, closed-schema conformance, binding fidelity, inactive-before-approval,
      later-gate exclusions, and checkpoint/replay; run the focused module and review the full diff.

Execution order: SUB-TASK-1 → SUB-TASK-2 → SUB-TASK-3.

Validation: focused pytest module plus existing gate-authority regressions; complete local diff
review confined to the three approved implementation files and the SCRUM-191 evidence workspace.
