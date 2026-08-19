# SCRUM-375 M-bM-^@M-^T Workflow run observability NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.workflow-run-observability` to an NA81-maturity
instruction-backed executable node with current-task test evidence binding the
SCRUM-375 brief (#310). The node already existed as a provenance-pinned SCRUM-252
control (`tools/node_architect/workflow_run_observability.py`) plus a closed
decision schema (`schemas/workflow-run-observability.schema.json`); this maturity
PR adds the missing NA81 test coverage and changelog provenance, leaving the
descriptor and existing source untouched (provenance-SHA trap avoided).

The observability decision projects exact-head CI evidence across pull-request
and post-merge push events while strictly distinguishing missing runs from
connector visibility gaps (family invariants):

- Exact-head SHA binding: runs whose `head_sha` differs from the expected exact
  head are excluded as mismatched, never counted as evidence.
- MISSING vs visibility gap: `RUNS_MISSING` (no matching exact runs) is distinct
  from `CONNECTOR_OBSERVABILITY_INCOMPLETE` (`EMPTY` returned without an exact
  filter, `ERROR`, `UNSUPPORTED`).
- Empty / unsupported lookup is observability-incomplete, never `CI_PENDING` or
  `PASS` (SUCCESS).
- Non-authoritative read-only projection: every authority field is fixed `False`.

## Guardrails

```text
WORKFLOW_RUN_OBSERVABILITY_IS_READ_ONLY_PROJECTION.
MISSING_RUNS_ARE_DISTINCT_FROM_CONNECTOR_VISIBILITY_GAPS.
EXACT_HEAD_SHA_BINDING_IS_REQUIRED_FOR_EVIDENCE.
SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY.
```

## Wiring

- New NA81 test `tests/test_workflow_run_observability_na81.py` binds the #310
  brief to the existing executable and validates the closed decision schema.
- Changelog fragment only; no `*.node.json` `description`/`source` fields edited.

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-375.
Targets pre-prod only; main is FORBIDDEN.
