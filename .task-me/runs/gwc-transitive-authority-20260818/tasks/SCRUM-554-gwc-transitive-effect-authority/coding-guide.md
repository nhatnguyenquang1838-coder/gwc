# Coding guide

## Existing patterns to preserve
- Preserve `validate_gate_action.py` as data-only fail-closed validation; it must never execute connector actions.
- Preserve canonical hashing/readback equality and existing trusted receipt requirements.
- Prefer schema + focused pure helper separation if causal closure logic makes the current validator too large.
- Keep current G0-G6 action mappings backward compatible as projections; capability is the semantic layer, not silent gate renumbering.

## Required semantic boundaries
- `destructive/delete/retention` is distinct from ordinary release/publish.
- `conditional + unknown + mutating` is potentially reachable, never silently ignored.
- legacy no-effect compatibility requires an explicit trusted action profile; absence of graph on trigger-capable/unknown actions is fail-closed.

## Forbidden shortcuts
- No invented semantic remapping.
- No implicit authority inheritance from a prior gate or successful historical workflow.
- No cross-repository authority borrowing.
- No treating absence of effect/readback evidence as PASS.
- No copied TaskController-only materialization semantics in GWC tests.
