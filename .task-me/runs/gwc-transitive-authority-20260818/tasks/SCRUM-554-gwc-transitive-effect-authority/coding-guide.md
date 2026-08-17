# Coding guide

## Existing patterns to preserve
- Preserve `validate_gate_action.py` as data-only fail-closed validation; it must never execute connector actions.
- Preserve canonical hashing/readback equality and existing G4 trusted receipt requirements.
- Prefer schema + focused helper separation if transitive closure logic makes the current validator too large.
- Keep current G0-G6 action mappings backward compatible; capability is an additional semantic layer, not silent gate renumbering.

## Forbidden shortcuts
- No invented semantic remapping.
- No implicit authority inheritance from a prior gate or successful historical workflow.
- No cross-repository authority borrowing.
- No treating absence of observable workflow evidence as PASS.
