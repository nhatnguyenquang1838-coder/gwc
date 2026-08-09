# NA81 Canonical DAG Contract v1.0

Status: normative
Task: SCRUM-383

## Invariant

`CANONICAL_DAG_EDGE = blocker/predecessor -> blocked/successor`

Every dependency consumer MUST operate on normalized edges with exactly two directional fields:

- `from`: blocker / predecessor
- `to`: blocked / successor

Raw Jira `inwardIssue` / `outwardIssue` fields and human-readable description prose are projection inputs only. They MUST NOT be consumed directly by scheduling, claimability, fastlane, or dependency validation logic.

## Jira Blocks normalization

For a current Jira issue `C` and a link whose type name is `Blocks`:

- `outwardIssue = X` normalizes to `{from: X, to: C}`.
- `inwardIssue = Y` normalizes to `{from: C, to: Y}`.

The endpoint field name describes which side of Jira's link object is present; it MUST NOT be interpreted as an arrow originating at the current issue.

## Projection rule

Jira is a live projection of the canonical edge set. A projector MUST create a Jira `Blocks` relationship using the canonical `from` issue as blocker and canonical `to` issue as blocked. A readback MUST normalize Jira links back to `{from,to}` and compare sets exactly.

Projection mismatch code: `DAG_PROJECTION_DRIFT`.

`DAG_EDGE_DIRECTION_AMBIGUOUS` MUST NOT be emitted for a valid `Blocks` link that can be normalized by this contract.

## Graph validation

For the NA81 execution graph, validation MUST prove:

- expected node set is SCRUM-298 through SCRUM-378 (81 nodes),
- no unknown endpoints,
- no self edges,
- no duplicate edges,
- no contradictory reverse pairs,
- no directed cycle,
- normalized Jira readback equals the canonical edge set.

## Regression lock: SCRUM-313

When reading SCRUM-313, Jira links with `outwardIssue` SCRUM-311 and SCRUM-312 MUST normalize as:

- `SCRUM-311 -> SCRUM-313`
- `SCRUM-312 -> SCRUM-313`

Any implementation producing the reverse direction violates this contract.
