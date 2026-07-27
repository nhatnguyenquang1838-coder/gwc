# Task-Me Host-Mode Contract v0.1

Status: G2 implementation for SCRUM-118.

## Authority
Task-Me is an implementation-planning provider. GWC gate artifacts and GitHub exact evidence remain authoritative.

## Input binding
A host request MUST bind target repository/ref/SHA, accepted UA snapshot id/digest, requirements/design versions, Task-Me package/source commit, output root, idempotency key, owner root, scope hash, checkpoint revision, lease token and fencing token.

## Output boundary
Task-Me may write only target-owned `.task-me/**`. It MUST NOT mutate product source, `.gwc/**`, `.ua/**`, Jira, Notion, Slack, branches, PRs, CI, releases, deployments, production data, credentials or secrets.

## DAG and failure behavior
Dependency DAGs must be acyclic or explicitly blocked. Stale UA snapshots, unverified targets, unknown dependencies, path escapes and ownership violations fail closed.

## Provenance
Every package/result records artifact id, parent artifact id, source repo/ref/SHA, tool package, tool source commit, schema version, owner root and generated timestamp.
