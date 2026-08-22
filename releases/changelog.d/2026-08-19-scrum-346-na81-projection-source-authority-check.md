# SCRUM-346 M-bM-^@M-^T Projection source authority check NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `sync_projection.projection-source-authority-check` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-346 brief (#281). The node already existed as a provenance-pinned
executable (`tools/node_architect/projection_source_authority_check.py`) with a
closed decision schema (`schemas/projection-source-authority-decision.schema.json`);
this maturity PR adds the missing NA81 test coverage and changelog provenance,
leaving the descriptor and existing source untouched (provenance-SHA trap
avoided).

The source-authority evaluator guarantees every projected field derives from an
allowed CANONICAL source evidence and can never become gate authority (family
invariants):

- Canonical-derived field -> READY, every authority grant fixed `False`.
- Projection-of-projection (field sourced from a PROJECTION authority class) ->
  fails closed (AUTHORITY_INVALID).
- Stale / untrusted / inference-derived source -> fails closed.
- Missing / non-canonical source -> fails closed.
- Digest mismatch / revision drift -> fails closed.
- Conflicts (duplicate ref, ambiguous status) -> fails closed.
- Invalid input -> fails closed.
- Deterministic digest / replay idempotency; inputs never mutated.
- Non-authoritative read-only projection; decision validates against the closed
  decision schema.

## Guardrails

```text
PROJECTION_OF_PROJECTION_IS_FORBIDDEN_AND_FAILS_CLOSED.
ONLY_CANONICAL_SOURCE_AUTHORITY_MAY_BACK_A_PROJECTED_FIELD.
STALE_OR_INFERRED_OR_UNVERIFIED_SOURCE_FAILS_CLOSED.
DIGEST_AND_REVISION_MUST_MATCH_THE_BOUND_CANONICAL_SOURCE.
SOURCE_AUTHORITY_CHECK_NEVER_GRANTS_GATE_AUTHORITY.
```

## Wiring

- New NA81 test `tests/test_projection_source_authority_check_na81.py` binds the
  #281 brief / Jira SCRUM-346 requirement matrix to the existing executable (28
  deterministic scenarios) and validates every decision against
  `schemas/projection-source-authority-decision.schema.json`.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited.

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-346.
Targets pre-prod only; main is FORBIDDEN.
