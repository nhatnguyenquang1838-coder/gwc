# Context7 Deep Research Notes — SCRUM-106

## Sources queried

- SQLite official documentation via Context7: transaction modes, locking, WAL, atomic commit, crash recovery and busy behavior.
- PostgreSQL current official documentation via Context7: transactions, isolation, row locks, advisory locks and serialization behavior.
- Supabase official documentation/examples via Context7: upsert conflict targets, RLS testing and migration verification.

## Design consequences

1. A storage transaction can be atomic while the client still has an ambiguous commit acknowledgement; every timeout-after-effect test therefore reloads durable state.
2. A session/advisory lock is not a durable lease. GWC needs persisted owner, expiry and monotonically increasing fencing token.
3. Idempotency prevents duplicate creation only when backed by a deterministic unique key/provider contract; it never removes the need for live-state readback.
4. SQLite single-writer contention and PostgreSQL serialization/lock failures are retryable only after current checkpoint/live-state reload.
5. Supabase RLS and unique constraints require negative tests proving unauthorized or duplicate attempts produce zero additional effect.
6. Cross-system external writes cannot be made atomic with the local checkpoint transaction; persist intent first, dispatch once, reconcile, then CAS checkpoint.
