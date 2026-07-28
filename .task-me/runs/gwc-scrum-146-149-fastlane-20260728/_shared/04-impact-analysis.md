# Shared impact analysis

- SCRUM-147 is the runtime correctness foundation: checkpoint revision/CAS,
  lease and fencing, crash boundaries, and replay/idempotency evidence.
- SCRUM-148 is a parallel decision-engine lane: canonical scenario registry,
  strict typed guards, route classification/ranking, deterministic digests, and
  explicit graph-size/path budgets. It must not create a second router.
- SCRUM-149 composes the runtime and router lanes through approved UA,
  Task-Me, BMAD and GitHub/CI host-mode contracts. It is no-production and
  offline-consumer validation only.
- SCRUM-146 is the final evidence lane. It consumes exact branch/head/merge/CI
  evidence and must distinguish executable proof, contract/validator proof,
  projection evidence, unverified state and deferred work.

The highest material risk is cross-lane scope expansion: these tasks must remain
contract, validator, test, fixture, evidence and bounded integration work. No
production data, deployment, migration, credentials, release or merge is in
scope.
