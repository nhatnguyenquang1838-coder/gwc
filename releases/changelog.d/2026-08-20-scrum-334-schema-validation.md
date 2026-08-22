## 2026-08-20 — SCRUM-334 schema validation (validation_quality.schema-validation)

### Added

- Implemented the missing canonical `validation_quality.schema-validation` behavior (SCRUM-334 / GitHub #269).
- Binds declared schema id + version + artifact/head provenance; PASS only for supported / current-compatible runtime-node schema + version.
- Fails closed on missing, malformed, ambiguous, unsupported/incompatible schema/version, and on malformed or version-drifting artifacts.
- Invalidates stale validation when artifact/schema/version/head drifts (same idempotency key, different inputs => prior result is stale).
- Deterministic replay / result digest.
- Explicit authority-negative: a PASS grants no G2/G3/G4/G5/G6, merge, deploy or production authority.
- Dedicated SCRUM-334 focused tests (`tests/test_validation_quality_schema_validation_m5.py`) covering all negative / drift / authority-negative cases.
- G3 fix: canonical runtime-node schema is self-validated against the Draft 2020-12 meta-schema (`Draft202012Validator.check_schema`) and identity-bound (`$id == RUNTIME_NODE_SCHEMA_ID`) at load; a defective canonical schema fails closed (no silent registration). Deterministic error ordering `(json_path, keyword, message)`.

### Safety

- This fragment documents the SCRUM-334 delta only.
- It does not grant protected-branch write, merge, auto-merge, deploy, release, production configuration, credential, migration, production-data, force-push, branch-deletion, or PR-base-change authority.
