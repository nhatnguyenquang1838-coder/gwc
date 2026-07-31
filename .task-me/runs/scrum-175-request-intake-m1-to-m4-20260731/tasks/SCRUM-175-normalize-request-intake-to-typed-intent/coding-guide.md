# Coding Guide

## Verified Files

- `core/node-architect/node-catalog/intake_context/request-intake.node.json`
- `tools/node_architect/validate_node_catalog_intake_context.py`
- `tests/test_node_catalog_intake_context.py`
- `core/node-architect/node-catalog/intake_context/README.md`
- `core/node-architect/runtime-graph-registry.json`
- `core/node-architect/node-registry.json`

## Implementation Order

1. Update the node descriptor first so the desired contract is explicit.
2. Update the validator second so the new fields are accepted and malformed/ambiguous cases still fail closed.
3. Add or adjust tests third so the new contract is pinned by regression coverage.
4. Refresh documentation last so it matches the final validated shape.

## Rules to Preserve

- Keep the node in `intake_context`.
- Keep `canonical` and `authority_boundary` aligned with the current family rules.
- Keep the gate set limited to `G0_CONTEXT`.
- Preserve deterministic behavior and fail closed on incomplete or ambiguous input.

## Validation Expectations

- Positive case: a canonical request normalizes to the same typed intake every time.
- Negative case: malformed input is rejected with a stable reason code.
- Negative case: ambiguous input is rejected instead of guessed.
- Structural case: family validator still enforces the nine-node family boundary.

## Prohibited Changes

- Do not add a parallel node family.
- Do not widen authority beyond read-only G0 context.
- Do not add production, deployment, migration, or credential handling.
- Do not change unrelated node families as opportunistic cleanup.
