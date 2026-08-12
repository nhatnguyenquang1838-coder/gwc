# SCRUM-304 intake_context.files-write-scope runtime contract upgrade

- Upgraded `intake_context.files-write-scope` from a legacy path-list renderer to the deterministic candidate write-scope evaluator (mirrors the SCRUM-303 `files-read-scope` contract).
- Derives the smallest candidate future write set bounded to verified task intent; records explicit exclusions and prohibited targets.
- Rejects protected/secret/control-plane/out-of-root paths deterministically via a built-in prohibited-target rule set.
- Binds repository/base/scope digest and prohibited targets for later G2 approval matching.
- Invalidates stale write scope after repository/UA drift or source-binding staleness (SCOPE_DRIFT).
- Proves output is candidate scope only: `read_only_projection`, `candidate_write_scope`, `authority_negative`, and all `*_authority_granted` fields are `false`.
- Kept `excluded_actions` (merge, deploy, release, credentials, secrets, migration, production_data, ...) for G2 envelope parity.
- Added `schemas/bounded-write-scope.schema.json` contract revision `files-write-scope/v2` and registered the runtime contract binding in the family validator.
- Added focused tests `tests/test_intake_context_files_write_scope.py` (READY scope, prohibited-target rejection, drift invalidation, scope-hash determinism, authority-negative, legacy payload compatibility).

Explicit exclusions retained: scheduler, database adapter, migration, deployment, production configuration, credentials, production data, merge, auto-merge, force-push, branch deletion, and PR base change.
