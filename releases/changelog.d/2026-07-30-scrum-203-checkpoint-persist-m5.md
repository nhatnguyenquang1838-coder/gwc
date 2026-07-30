# SCRUM-203 — checkpoint-persist M5 slice

- Added replay-safe checkpoint store primitives.
- Added CAS mismatch protection with no event mutation on conflict.
- Added crash-after-commit readback behavior to prevent duplicate effects.
- Added runtime checkpoint and runtime event schemas.
- Added scoped unittest coverage for CAS, append-only event binding and replay readback.

Boundaries: no main write, merge, deploy, release, production data, secrets or migration.
