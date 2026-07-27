# GitHub G5/G6 Jira Projection Contract v0.1

GitHub is authoritative for repository refs, PR heads, merge commits and CI. GWC gate artifacts and exact approvals are authoritative for G0-G6. Jira, Slack and Notion are projections only.

## Exact-state binding
Evidence records bind repository, expected/observed main SHA, expected/observed PR head SHA, expected/observed merge SHA and workflow/job conclusions. Drift fails closed.

## G5/G6 separation
G5 is post-merge verification only. G6 is required for production, database, secret, migration, destructive, release or deployment operations.

## Failure codes
`STALE_MAIN_SHA`, `PR_HEAD_DRIFT`, `CI_UNAVAILABLE_AT_CHECK`, `VALIDATION_FAILED`, `MERGE_SHA_MISMATCH`, `PROJECTION_WRITE_FAILED`, `PROJECTION_AUTHORITY_LEAKAGE`, `G6_REQUIRED`.
