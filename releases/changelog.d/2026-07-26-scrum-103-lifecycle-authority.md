# SCRUM-103 lifecycle and authority enforcement

## Added

- Explicit state transitions for G3 review, G4 merge, read-only or manual G5,
  and conditional G6 operations.
- Fail-closed gate-action authority schema and validator binding task,
  repository, base/head SHAs, scope hash, expiry, actor, and readback.
- Deterministic G5 candidate resolver and normalized status-evidence validator
  that reject stale or unrelated workflow runs.

## Changed

- The GWC package now exports the lifecycle map, action-authority controls,
  and G5 status controls without changing `package_version: "1.16.0"`.

## Safety

- Jira remains a work-tracking projection; it does not grant GWC gate
  authority.
- No merge, deployment, production configuration, credentials, migrations, or
  production-data operations are authorized by this change.
