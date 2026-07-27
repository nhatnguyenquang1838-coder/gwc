# UA Host-Mode Contract v0.1

Status: G2 implementation for SCRUM-117.

## Authority
GWC gate artifacts and GitHub exact evidence remain authoritative. UA is a derived knowledge provider only.

## Request binding
A host request MUST include task id, run id, target repository/ref/SHA, UA package/source commit, configuration digest, output root, idempotency key, owner root, scope hash, checkpoint revision, lease token and fencing token.

## Output boundary
UA may read source and write only target-owned `.ua/**`. It MUST NOT mutate product source, `.gwc/**`, `.task-me/**`, Jira, Notion, Slack, branch state, PR state, CI state, releases, deployment, production data, credentials or secrets.

## Freshness
Snapshots are accepted only when target SHA, UA source commit and configuration digest match the request. Stale or mismatched inputs fail closed or return REFRESH_REQUIRED.

## Provenance
Every output records artifact id, parent artifact id, source repo/ref/SHA, tool package, tool source commit, schema version, owner root and generated timestamp.
