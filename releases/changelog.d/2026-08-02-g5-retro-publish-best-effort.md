# G5 retrospective recovery trace publish hotfix

- Treats retrospective G5 recovery artifact upload as the canonical machine evidence once validation succeeds.
- Makes the final PR receipt publication step best-effort: a `403 Resource not accessible by integration` now emits a warning and step summary instead of failing the whole run.
- Preserves guardrails: no normal G4 authority backfill, no new merge authority, no manual G5 action, no deployment/release/production config/data/migration, and no G6 authority.
