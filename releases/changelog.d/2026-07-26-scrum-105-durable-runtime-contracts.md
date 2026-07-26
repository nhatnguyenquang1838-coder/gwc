## 2026-07-26 — SCRUM-105 durable runtime store and adapter contracts

### Added

- Added provider-neutral durable run, event, checkpoint, pending-action, adapter,
  and storage-migration schemas for the P2-K1 contract lane.
- Defined CAS, lease, fencing, idempotency, readback, version pinning, and
  SQLite-to-PostgreSQL/Supabase compatibility semantics without implementing a
  runtime engine or live migration.
- Added focused schema/invariant tests and package exports.

### Safety

- Extends `REVAMP-GWC-012` checkpoint/runtime contract lineage.
- No merge, deploy, release, production configuration, credentials, migrations,
  or production-data operations are authorized by this change.
