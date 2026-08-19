# SCRUM-340 M‑05 Blocker severity classification NA81 semantics

## Type

```text
feature
```

## Summary

Implements the missing SCRUM-340 (NA81-F5) semantics for the
`validation_quality.blocker-severity-classification` node (#275): classify
validation/review findings against a versioned severity/terminality policy with
stable rule IDs and emit a deterministic, fail-closed next-route decision.

The descriptor (`core/node-architect/node-catalog/validation_quality/
blocker-severity-classification.node.json`) is the catalog identity record and
is left untouched — its `description`/`source` provenance SHA is not modified
(provenance-SHA trap avoided). The classification taxonomy lives in the
versioned helper module
`tools/node_architect/blocker_severity_classification.py` (POLICY_VERSION
`2026-08-14-r10`), so taxonomy changes do not require editing descriptor
provenance and policy drift is detectable.

Fail-closed guarantees (node contract for SCRUM-340 / #275):

- Unmatched authority / evidence / data-integrity findings BLOCK and are never
  silently waived.
- Any finding in a terminal category (authority / evidence / data-integrity)
  blocks regardless of declared severity.
- Conflicting rules for one finding BLOCK.
- A mismatched policy_version BLOCKS (`POLICY_DRIFT`).
- Unknown rule ID or malformed finding BLOCKS (`UNMATCHED`).
- PASS only when every open finding is matched by a known rule and resolves to
  an advisory (sub-threshold, non-terminal) severity.

The classifier is pure and read-only: no connector call, network request,
filesystem mutation, Jira transition, branch/PR action, approval, merge,
deployment or production operation. Every authority field is fixed `False`.

## Guardrails

```text
NA81_BLOCKER_SEVERITY_CLASSIFICATION_FAILS_CLOSED.
NA81_UNMATCHED_AUTHORITY_EVIDENCE_DATA_INTEGRITY_FINDINGS_BLOCK.
NA81_NO_SILENT_BLOCKER_WAIVER.
NA81_POLICY_DRIFT_IS_DETECTABLE_AND_BLOCKS.
NA81_BLOCKER_SEVERITY_CLASSIFICATION_GRANT_NO_AUTHORITY.
```

## Wiring

- New executable
  `tools/node_architect/blocker_severity_classification.py` with
  `classify_blocker_severity(...)`.
- New focused test
  `tests/test_validation_quality_blocker_severity_classification_m5.py`
  binding the SCRUM-340 brief (known severity classes, unmatched finding,
  conflicting rules, authority/evidence/data-integrity boundary, policy drift,
  replay determinism).
- Changelog fragment only; no `*.node.json` `description`/`source` fields
  edited and no registry `source_sha` mutated (provenance-SHA trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-340.
Targets pre-prod only; main is FORBIDDEN.
