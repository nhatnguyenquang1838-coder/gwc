# SCRUM-208 Tasks

- [x] Define the closed CAS decision schema.
- [x] Implement the pure CAS evaluator.
- [x] Add backward-compatible checkpoint-store integration.
- [x] Add idempotent commit-before-response replay protection.
- [x] Add focused and legacy regression tests.
- [x] Record task-scoped G0/G1/G2 artifacts and changelog.
- [x] Close G3 REV-1 by binding `cas_context` to canonical `CheckpointInput` and store identity.
- [x] Close G3 REV-2 by binding effects and validating ownership before replay.
- [x] Add adversarial context-conflict, idempotency-collision, and stale-replay tests.
- [ ] Obtain new G3 authority after the exact repair-head CI completes.
