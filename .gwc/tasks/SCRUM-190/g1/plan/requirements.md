# SCRUM-190 — Requirements (Task Me plan)

Task: [MAT-F2-N07] `gate_authority.gate-transition-decision` (M2 → M5)
Parent: SCRUM-167
Repository: nhatnguyenquang1838-coder/gwc
Protected base: f6ef9a1ef30b40d110b4db9d34dddddb12b19c59
Selected option: OPT-1
Risk class: R2

## Functional requirements

1. Evaluate a replay-safe `gate_transition_decision` from the current gate state, gate evidence,
   and F2 authority inputs. Identical inputs must always produce an identical decision.
2. The decision outcome set is exactly `PASS`, `BLOCK`, `CONTINUE`, `AWAITING_APPROVAL`, and
   `NOT_APPLICABLE`.
3. Every decision identifies the resolved next lifecycle node, or `null` with an explicit reason
   code when no next node applies.
4. Next-node topology is resolved exclusively from `core/task-lifecycle/gate-transition-map.yaml`;
   no topology is inferred, hardcoded, or substituted.
5. The node never performs, applies, or persists a gate transition; it only decides.
6. Checkpoint/replay: the evaluator emits a replay digest so the same decision can be recomputed
   and compared after a crash or resume.
7. Fail closed: missing, invalid, drifted, or unapproved evidence yields `BLOCK`, never `PASS`.

## Non-functional requirements

- Pure Python standard library plus the repository's existing `jsonschema` and PyYAML usage;
  no new dependencies.
- Deterministic ordering and stable serialization for all collections.
- No connector call, no repository write, no execution.

## Dependencies

SCRUM-184, SCRUM-186, SCRUM-188, SCRUM-189, SCRUM-191.

## Acceptance criteria mapping

- AC-1 → decision schema (`schemas/gate-transition-decision.schema.json`)
- AC-2 → closed outcome set and next-node identification
- AC-3 → map-driven topology resolution
- AC-4 → never performs a transition, no later-gate authority
- AC-5 → checkpoint/replay determinism
- AC-6 → focused M5 tests pass
