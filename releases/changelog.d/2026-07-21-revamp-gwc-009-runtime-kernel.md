## 2026-07-21 — REVAMP-GWC-009 runtime kernel schemas

### Added

- Runtime Kernel contract for node-oriented GWC execution before catalog expansion.
- Runtime kernel, runtime event, transition envelope, and node pack schemas.
- Stdlib-only runtime kernel validator and regression tests.
- GWC package entries for the runtime kernel artifacts while keeping `package_version: "1.16.0"`.

### Safety

- This fragment documents PR #61 / REVAMP-GWC-009 only.
- This change grants no protected-branch write outside G2, merge, auto-merge, deploy, release, production configuration, credential, migration, production-data, force-push, branch-deletion, or PR-base-change authority.
