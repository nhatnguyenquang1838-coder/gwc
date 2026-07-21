
---
extension_id: rental-home-conventions
version: "1.0"
authoritative: false
extends_profile: rental-home
core_policy: CODING-PROJECT-GOVERNANCE@1.0
core_sha256: ea3e44ac2d948b8439e9768bea4f5dda8474a34e914592130965083792a5ee48
mode: tighten_only
---

# Rental Home Project Extension

## Source of truth

- Read protected-base `AGENTS.md` first.
- When this extension conflicts with protected-base `AGENTS.md`, stop and
  report the conflict; do not silently choose.
- Use the spec-driven format included in this package for Kiro-style specs.

## Workspace isolation

Every task uses:

```text
/mnt/data/rental_home_sessions/<YYYYMMDD-HHMM>-<TASK-ID>/
```

Every branch uses a separate folder and worktree. Never share one working
directory between branches.

## Data and privacy

- Preserve Supabase RLS.
- Enforce home, room, contract, invoice, and tenant ownership server-side.
- Never expose service-role credentials to the client.
- Treat schema changes and migrations as separately scoped work.
- Production-data reads or writes require `G6_PRODUCTION_DATA`.
- Destructive operations require dependency preview, explicit scope, backup or
  rollback evidence, and auditability.

## Application conventions

- Reuse existing UI components and established patterns.
- Do not create duplicate CTA implementations when a shared component exists.
- Preserve role and home boundaries.
- Keep IDs technical and readable.
- Design mobile behavior explicitly.
- Prevent duplicate asynchronous CTA requests with loading and disabled states.

## Validation

Applicable work must include:

- typecheck;
- tests;
- build;
- RLS and authorization denial cases;
- migration verification;
- mobile layout checks;
- empty, loading, error, and permission states;
- complete diff review.

## Activation condition

This extension does not control repository write enablement. Follow the
active project profile and protected-base governance for `write_enabled` and
identity status.
