# DW SUPER E2E Replayable Pilot Contract v0.1

## Authority model

GWC remains authoritative for G0-G6. GitHub remains authoritative for repository refs, PR heads, merge commits and CI. UA, Task-Me and BMAD are bounded providers. Jira, Slack and Notion are projections only and cannot grant gate authority.

## Pilot boundary

`PILOT-121-A` is a no-production evidence pilot. It may create task-scoped repository artifacts, validators, examples, a guarded branch and a Draft PR. It must not deploy, release, publish, mutate production data/configuration, access secrets, run migrations, perform destructive actions, force-push, delete branches, change PR bases, or auto-merge.

## Replayability

Each node records provider, version binding, input hash, output hash, decision, checkpoint revision and idempotency key. Replay passes only when the route and decisions are deterministic or when live-state divergence is typed and accepted as a non-side-effect replay difference.

## Required fault coverage

The pilot must demonstrate stale artifact rejection, changed PR head rejection, unavailable exact-commit CI classification, duplicate projection retry handling, Slack unavailable fallback, interrupted execution resume, and BMAD scope-violation rejection.
