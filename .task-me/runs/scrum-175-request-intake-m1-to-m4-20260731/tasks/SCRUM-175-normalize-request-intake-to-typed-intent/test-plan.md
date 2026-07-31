# Test Plan

## Coverage Goals

- Deterministic normalization for the canonical request shape.
- Rejection of malformed payloads.
- Rejection of ambiguous payloads.
- Stable reason-code emission for each failure mode.
- Family validator still accepts the real node set and rejects authority or gate drift.

## Test Cases

1. Canonical request normalizes to the expected typed fact set.
2. The same canonical request run twice yields the same normalized result.
3. Missing or malformed intake fields fail closed.
4. Conflicting intent or exclusion signals fail closed as ambiguous.
5. A node with a widened authority boundary is rejected.
6. A node with a non-G0 gate is rejected.
7. The real family still validates successfully after the contract expansion.

## Validation Commands

```bash
python tools/node_architect/validate_node_catalog_intake_context.py
python -m unittest tests/test_node_catalog_intake_context.py
python -m unittest tests/test_node_catalog_package_export.py
git diff --check
```

## Evidence To Capture

- Exact repository head SHA used for the final validation run.
- Validator output for the intake-context family.
- Unit-test output for canonical and negative cases.
- Any failure codes emitted for malformed or ambiguous input.

## Residual Risk

If the richer contract needs a helper or schema artifact, the test suite should make that need visible rather than hiding it behind a permissive validator change.
