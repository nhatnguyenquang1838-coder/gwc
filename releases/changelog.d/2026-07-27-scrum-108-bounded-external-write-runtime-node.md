# SCRUM-108 bounded external-write runtime node

- Adds a provider-neutral bounded external-write classifier for persisted intent, idempotency, exact scope binding, live-state readback reconciliation, duplicate-worker prevention, stale checkpoint fencing, and ambiguous timeout human handoff.
- Adds focused unit coverage for validation failure, timeout-before-effect, timeout-after-effect reconciliation, duplicate-worker single-effect handling, stale checkpoint rejection, ambiguous post-state handling, and human takeover replay guards.
- Does not add connector clients, migrations, credentials, deployment hooks, production configuration, or production-data access.
