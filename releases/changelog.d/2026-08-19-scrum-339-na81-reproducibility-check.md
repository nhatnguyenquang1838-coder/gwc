feat(gwc): SCRUM-339 NA81-F5 reproducibility-check NA81 semantics

Implement the missing SCRUM-339 (NA81-F5-N05 / node #274) NA81 semantics on
top of the existing `validation_quality.reproducibility-check` node descriptor.
Predecessors SCRUM-335 (#270) and SCRUM-336 (#271) are already Done and their
evidence lives in current pre-prod; this change implements only the missing
rerun comparison / difference-report behaviour.

New behaviour (DELTA_REQUIRED, backward-compatible -- the node descriptor is
data-only and untouched; provenance SHA preserved):

- `tools/node_architect/reproducibility_check.py` adds:
  * `check_reproducibility(...)` -- core fail-closed reproducibility decision
    comparing a captured validation state against a rerun across the stable
    dimensions (tool / runtime / input / dependency / policy / environment).
    Missing environment/toolchain evidence (REPRO_ENVIRONMENT_EVIDENCE_MISSING)
    or unexplained result divergence (REPRO_NONDETERMINISM) MUST NOT PASS.
    Declared volatile fields may differ without blocking. Deterministic digest,
    replay cache and explicit authority boundary (merge/deploy/production=False).
  * `check_reproducibility_na81(...)` -- NA81 layer reusing the core and adding
    the explicit SCRUM-339 NA81-F5 guarantees: deterministic / replay
    idempotency, explicit authority boundary, fail-closed (NA81_FAIL_CLOSED when
    any reproducibility failure is present, never silently passes), and
    explicit non-authoritative guarantee with a stable repro_digest.

Required test scenarios covered by the focused test:
- equivalent rerun -> PASS / REPRO_ACCEPTED;
- tool / input / dependency / policy drift -> BLOCKED with the matching reason;
- missing environment/toolchain evidence -> BLOCKED;
- allowed volatile-only differences -> PASS with REPRO_VOLATILE_DIFF.

New files:
- tests/test_validation_quality_reproducibility_check_m5.py (focused NA81 tests)

Updated files:
- tools/node_architect/reproducibility_check.py (check_reproducibility,
  check_reproducibility_na81)

This change is mechanical only -- no autonomous merge / main action. The PR
targets pre-prod only; main is FORBIDDEN.

Parent authority: R10 (issue #232), run SCRUM-288-NA81-RECERT-20260814-R10,
task SCRUM-339. This fragment grants no merge, deploy, release, production
configuration, credential, migration, or production-data authority.
