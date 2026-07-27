# Requirements

## Objective
Define the Task-Me host-mode contract so impact analysis, decomposition, coding guidance and validation planning are generated from an exact UA snapshot and bounded to target-owned `.task-me/**` outputs.

## Acceptance criteria
- Bind exact UA snapshot id/digest, target SHA, requirements/design versions and Task-Me package/source commit.
- Output only `.task-me/**` references.
- Cyclic DAGs, stale UA snapshots and path escapes fail closed.
- Estimates expose assumptions rather than unsupported precision.
- Task-Me cannot mutate product source, `.gwc/**`, Jira, Notion, Slack or Git delivery state.
