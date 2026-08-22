# SCRUM-336 — validation_quality.unit-test-mapping NA81 executable route

## Type

```text
feature
```

## Area

```text
validation_quality
```

## Summary

Implements the missing deterministic executable route for the
`validation_quality.unit-test-mapping` node (SCRUM-336 / GitHub issue #271) as
an NA81-maturity, instruction-backed decision helper. The node already existed
as a provenance-pinned descriptor
(`core/node-architect/node-catalog/validation_quality/unit-test-mapping.node.json`)
with no executable route; this PR adds the deterministic
`tools/node_architect/unit_test_mapping.py` (`map_unit_tests`), its closed JSON
Schema (`schemas/unit-test-mapping-decision.schema.json`) and current-task m5
test evidence (`tests/test_validation_quality_unit_test_mapping_m5.py`).

The route maps changed runtime catalog artifacts to the MINIMUM mandatory
executable unit tests with explicit rule IDs and a DELTA_REQUIRED /
VERIFIED_REUSE classification (historical SCRUM-213 is reuse evidence only). It
is fail-closed:

- Unmapped runtime behavior BLOCKS (`UNMAPPED_CHANGE`).
- A mapped required test absent from the inventory BLOCKS (`MISSING_REQUIRED_TEST`,
  covering deleted/missing tests).
- Overlapping/ambiguous rules for one artifact BLOCK (`MAPPING_CONFLICT`).
- Docs-only changes (markdown / docs dir / README / CHANGELOG) are handled
  EXPLICITLY (`DOCS_ONLY`), never guessed into requiring tests.
- Policy drift is detected against an expected policy digest (`POLICY_DRIFT`).
- Invalid identity / policy input fails closed (`INVALID_INPUT`).
- Replay cache: identical idempotency_key + input_digest yields an identical
  `evidence_digest` with `replayed=True`; a conflicting identity under the same
  key fails closed (`CONFLICTING_IDENTITY`).

No merge / deployment / production authority is granted (the three
`*_granted` flags are fixed `False`).

## Guardrails

VERIFIED_REUSE of the node descriptor and existing sibling decision helpers
(`capture_ci_evidence`, `decide_g3_pass`); new DELTA_REQUIRED mapping rules
implemented without fake coverage or no-op PR. The `*.node.json` descriptor
`description`/`source` fields are untouched (provenance-SHA trap avoided).

## Wiring

- New `tools/node_architect/unit_test_mapping.py` exporting `map_unit_tests`.
- New `schemas/unit-test-mapping-decision.schema.json` (Draft202012).
- New `tests/test_validation_quality_unit_test_mapping_m5.py` binding the #271
  brief to the executable and validating the closed decision schema.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited.

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-336.
Targets pre-prod only; main is FORBIDDEN.
