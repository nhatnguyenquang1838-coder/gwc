# Coding guide

## Existing patterns to preserve
- Preserve `validate_gate_action.py` as data-only fail-closed validation; it must never execute connector actions.
- Preserve canonical hashing/readback equality and existing trusted receipt requirements.
- Prefer schema + focused pure helper separation if causal closure logic makes the current validator too large.
- Keep current G0-G6 action mappings backward compatible as projections; capability is the semantic layer, not silent gate renumbering.

## Required semantic boundaries
- `destructive/delete/retention` is distinct from ordinary release/publish.
- `conditional + unknown + mutating` is potentially reachable, never silently ignored.
- legacy compatibility requires an explicit versioned trusted effect profile. `NO_TRANSITIVE_MUTATION` is only the trivial profile; trigger-capable actions may remain compatible only when a `BOUNDED_TRANSITIVE_EFFECTS` profile completely enumerates reachable/potentially reachable effects and proves they are within current authority or independently authorized.
- absence of both an effect graph and a complete trusted effect profile on trigger-capable/unknown actions is fail-closed.

## Forbidden shortcuts
- No invented semantic remapping.
- No implicit authority inheritance from a prior gate or successful historical workflow.
- No cross-repository authority borrowing.
- No treating absence of effect/readback evidence as PASS.
- No copied TaskController-only materialization semantics in GWC tests.
