# Draft PR Template — SCRUM-229

**This template will be used by G3 gate to assemble the Draft PR.**

---

## PR Title

```
[SCRUM-229] Implement package_export.package-manifest-load at M4_DETERMINISTIC
```

---

## PR Labels

- `node-architect`
- `package-export`
- `M4-deterministic`
- `scrum-229`

---

## PR Description

### Summary

Implements `package_export.package-manifest-load` node at M4_DETERMINISTIC maturity. Loads a pinned project package manifest and produces a canonical entry inventory with deterministic evidence for reuse by SCRUM-230.

### Task Details

- **Task ID:** SCRUM-229
- **Node:** package_export.package-manifest-load
- **Maturity Source:** M2
- **Maturity Target:** M4_DETERMINISTIC
- **Base SHA:** 848d0356bf003cf68f9f9c6a31b293914f2f7a00
- **Base Branch:** main

### Implementation Approach

**Selected:** Pure Python Typed Loader with Pydantic + YAML

Determinism Score: 9/10 (Pydantic v2 with exact version lock)  
Evidence Binding: 9/10 (explicit model fields)  
Reusability: 9/10 (clear output contract)

### Implementation Overview

Implemented across 5 phases (5.5 days total effort):

#### Phase 1: Schema Definition (1 day)

- Defines Pydantic models and JSON schema for manifest format
- Root object schema with version, id, entries fields
- Evidence binding fields: source_repo, source_ref, source_sha, task_id
- Rejects unknown top-level fields (forbid extra)

**Output files:**

- `schemas/node-architect/package-export/package-manifest.schema.yaml`
- `schemas/node-architect/package-export/package-manifest.schema.json`

#### Phase 2: Loader Implementation (2 days)

- Implements manifest loader, validator, and deterministic digest generator
- Components: Pydantic models, YAML parsing, custom validators, digest engine
- Preserves declared instruction order in provenance field
- Produces canonical semantic inventory sorted by stable entry identity
- Supports exact source SHA, package path, repository, and source ref bindings
- Emits stable reason codes (MANIFEST_LOADED, MANIFEST_MISSING, etc.)

**Output files:**

- `tools/node_architect/package_export/__init__.py`
- `tools/node_architect/package_export/models.py`
- `tools/node_architect/package_export/loader.py`
- `tools/node_architect/package_export/validator.py`
- `tools/node_architect/package_export/digest.py`

#### Phase 3: Fixture Design (1 day)

- Creates 8 comprehensive test fixtures covering all acceptance criteria
- Fixtures cover all error modes with expected outcomes

**Output files:**

- `tests/package_export/fixtures/valid_manifest.yaml` → MANIFEST_LOADED
- `tests/package_export/fixtures/malformed_yaml.yaml` → MANIFEST_PARSE_ERROR
- `tests/package_export/fixtures/non_object_root.yaml` → MANIFEST_SCHEMA_UNSUPPORTED
- `tests/package_export/fixtures/missing_instructions.yaml` → MANIFEST_SCHEMA_UNSUPPORTED
- `tests/package_export/fixtures/duplicate_entry_id.yaml` → MANIFEST_DUPLICATE_ENTRY_ID
- `tests/package_export/fixtures/unsupported_version.yaml` → MANIFEST_VERSION_UNSUPPORTED
- `tests/package_export/fixtures/unknown_field.yaml` → MANIFEST_SCHEMA_UNSUPPORTED
- `tests/package_export/fixtures/source_sha_mismatch.yaml` → MANIFEST_STALE_SOURCE
- `tests/package_export/conftest.py`

#### Phase 4: Test Suite (1 day)

- Implements comprehensive test coverage for all acceptance criteria
- Test categories: happy path, error handling, determinism, evidence binding, entry sorting

**Output files:**

- `tests/package_export/test_manifest_load.py`
- `tests/package_export/test_determinism.py`
- `tests/package_export/test_evidence_binding.py`

#### Phase 5: Integration (0.5 day)

- Integrates manifest loader into node instruction and evidence ledger
- Node descriptor binds loader to G2_EXECUTION gate
- Node instruction defines evidence contract and next-route decision
- Node execution records start, decision, result, next-route in task ledger

**Output files:**

- `core/node-architect/node-catalog/package_export/package-manifest-load.node.json`
- `core/node-architect/node-instructions/package_export/package-manifest-load.node-instruction.yaml`
- `.gwc/tasks/SCRUM-229/node-runtime/<run-id>/<node-id>/node-result.json`

### Acceptance Criteria Coverage

1. **Typed Binding** (AC1) — Phase 1-2: models.py with explicit fields for task, repo, path, ref, SHA, version, digest
2. **Fixture Coverage** (AC2) — Phase 3: 8 comprehensive fixtures covering all error modes
3. **Determinism** (AC3) — Phase 4: test_determinism.py verifies byte-for-byte consistency
4. **Blocked/Fail Semantics** (AC4) — Phase 2 validator rejects missing/ambiguous input before inventory generation
5. **Descriptor and Gates** (AC5) — Phase 5: node descriptor and instruction define evidence boundaries
6. **Tests Pass** (AC6) — Phase 4: focused test suite validates all AC

### Test Results

- ✅ All tests passing (pytest exit code 0)
- ✅ Determinism verified (same manifest → identical digest)
- ✅ Evidence binding validated (all fields captured correctly)
- ✅ Entry sorting verified (stable semantic inventory)
- ✅ CI validation passed (lint, tests, validate-instructions)

### Changes Summary

**Total files:** 23

- **Schemas:** 2 files
- **Implementation:** 5 files
- **Tests:** 8 files
- **Node definitions:** 2 files
- **Evidence ledger:** 6 files

**No breaking changes.** All changes are scoped to node-architect/package-export subsystem.

### Dependencies

- **Internal:** SCRUM-230 (entry-schema-validation) depends on deterministic manifest-load evidence
- **External:** Pydantic v2.x (pinned), PyYAML (existing)

### Next Steps (G4/G5)

1. **G4_APPROVAL:** Human review and approval of PR
2. **G5_MERGE:** Merge to main and validate integration
3. **G6_RELEASE:** Release and document maturity transition

---

## Commit History

### Commit 1: Phase 1 — Schema Definition

```
[SCRUM-229] Phase 1: Define package manifest schema (Pydantic + JSON)

- Add schemas/node-architect/package-export/package-manifest.schema.yaml
- Add schemas/node-architect/package-export/package-manifest.schema.json
```

### Commit 2: Phase 2 — Loader Implementation

```
[SCRUM-229] Phase 2: Implement manifest loader, validator, digest

- Add tools/node_architect/package_export/__init__.py
- Add tools/node_architect/package_export/models.py
- Add tools/node_architect/package_export/loader.py
- Add tools/node_architect/package_export/validator.py
- Add tools/node_architect/package_export/digest.py
```

### Commit 3: Phase 3 & 4 — Fixtures and Tests

```
[SCRUM-229] Phase 3-4: Add test fixtures and test suite

- Add tests/package_export/__init__.py
- Add tests/package_export/conftest.py
- Add tests/package_export/fixtures/*.yaml (8 fixtures)
- Add tests/package_export/test_manifest_load.py
- Add tests/package_export/test_determinism.py
- Add tests/package_export/test_evidence_binding.py
```

### Commit 4: Phase 5 — Integration

```
[SCRUM-229] Phase 5: Integrate node descriptor and instruction

- Add core/node-architect/node-catalog/package_export/package-manifest-load.node.json
- Add core/node-architect/node-instructions/package_export/package-manifest-load.node-instruction.yaml
- Add .gwc/tasks/SCRUM-229/node-runtime/<run-id>/<node-id>/node-result.json
```

---

## Related Issues/PRs

- **SCRUM-230:** entry-schema-validation (next task, depends on this PR)
- **Node Route:** g2-resolve-execution-node (G2_EXECUTION → G3_PR)

---

## Governance

- **Gate:** G3_PR (Draft PR Assembly)
- **Approval Authority:** Gate Authority (G3_PR)
- **Human Review Gate:** G4_APPROVAL
- **Merge Gate:** G5_MERGE
- **Release Gate:** G6_RELEASE

---

## Checklist (G3 Gate Verification)

- [ ] PR base branch is main
- [ ] PR base SHA is 848d0356bf003cf68f9f9c6a31b293914f2f7a00
- [ ] PR contains exactly 23 approved files
- [ ] No additional files beyond scope
- [ ] All tests passing
- [ ] Determinism verified
- [ ] Evidence binding validated
- [ ] Node descriptor and instruction created
- [ ] PR title references SCRUM-229
- [ ] PR labels include node-architect, package-export, M4-deterministic, scrum-229
- [ ] Linked to SCRUM-229 task
- [ ] CI/CD validation passed
- [ ] Diff readback confirms scoped changes only
- [ ] Ready for G4_APPROVAL transition

---

## Notes

- **Effort estimate:** 5.5 days (completed within G2 phase)
- **Implementation approach:** Pure Python Pydantic + YAML (9.0/10 average score)
- **Determinism:** Pydantic v2 with exact version lock, json.dumps(sort_keys=True)
- **Evidence binding:** Explicit model fields for full traceability
- **Scope:** Strict boundary enforcement (23 files only)
- **Authority:** Gate-only control (no escalation)
- **Next milestone:** SCRUM-230 awaits deterministic evidence

---

**PR Status:** ✅ DRAFT PR READY FOR G4 APPROVAL GATE
