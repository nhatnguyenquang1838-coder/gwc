# G2 EXECUTION COMMAND — SCRUM-229

**Task:** [MAT-F7-N01] package_export.package-manifest-load — M2 → M4_DETERMINISTIC  
**Gate:** G2_EXECUTION  
**Status:** APPROVED FOR EXECUTION  
**Issued:** 2026-08-03T00:51:00+0700  
**Expires:** 2026-08-04T00:51:00+0700  
**Approver:** GitHub Copilot  
**Authority:** Gate Authority (G2_EXECUTION)

---

## EXECUTION COMMAND

```
PROCEED WITH G2_EXECUTION
│
├─ REPOSITORY: nhatnguyenquang1838-coder/gwc
├─ BASE_BRANCH: main
├─ BASE_SHA: 848d0356bf003cf68f9f9c6a31b293914f2f7a00 (VERIFIED)
├─ WORKING_MODE: local_agent
├─ EXECUTOR: GitHub Copilot
│
├─ STEP 1: CREATE ISOLATED WORKTREE FROM PROTECTED BASE
│  ├─ Worktree path: .gwc/worktrees/SCRUM-229-package-manifest-load
│  ├─ Base SHA: 848d0356bf003cf68f9f9c6a31b293914f2f7a00
│  ├─ Isolation strategy: DETACHED (no shared HEAD)
│  └─ Status: AUTHORIZED
│
├─ STEP 2: CREATE FEATURE BRANCH
│  ├─ Branch name: feature/scrum-229-package-manifest-load
│  ├─ From SHA: 848d0356bf003cf68f9f9c6a31b293914f2f7a00
│  ├─ Commit strategy: ATOMIC_SCOPE
│  └─ Status: AUTHORIZED
│
├─ STEP 3: EXECUTE IMPLEMENTATION PHASES (5.5 DAYS EFFORT)
│  │
│  ├─ PHASE 1: SCHEMA DEFINITION (1 DAY)
│  │  ├─ Output files:
│  │  │  ├─ schemas/node-architect/package-export/package-manifest.schema.yaml
│  │  │  └─ schemas/node-architect/package-export/package-manifest.schema.json
│  │  ├─ Requirements:
│  │  │  ├─ Root object schema with version, id, entries fields
│  │  │  ├─ Version string (semantic versioning)
│  │  │  ├─ Entries list with id, name, type (mandatory)
│  │  │  ├─ Evidence fields: source_repo, source_ref, source_sha, task_id
│  │  │  └─ Forbid extra fields
│  │  └─ Status: AUTHORIZED
│  │
│  ├─ PHASE 2: LOADER IMPLEMENTATION (2 DAYS)
│  │  ├─ Output files:
│  │  │  ├─ tools/node_architect/package_export/__init__.py
│  │  │  ├─ tools/node_architect/package_export/models.py
│  │  │  ├─ tools/node_architect/package_export/loader.py
│  │  │  ├─ tools/node_architect/package_export/validator.py
│  │  │  └─ tools/node_architect/package_export/digest.py
│  │  ├─ Components:
│  │  │  ├─ models.py: Pydantic v2 models with custom validators
│  │  │  ├─ loader.py: YAML parsing + Pydantic validation
│  │  │  ├─ validator.py: Business logic (duplicates, versions, source binding)
│  │  │  └─ digest.py: Deterministic digest (json.dumps sort_keys=True)
│  │  ├─ Requirements:
│  │  │  ├─ Preserve declared order in provenance
│  │  │  ├─ Canonical semantic inventory (sorted by entry ID)
│  │  │  ├─ Source SHA + path + repo + ref bindings
│  │  │  └─ Stable reason codes (7 codes)
│  │  └─ Status: AUTHORIZED
│  │
│  ├─ PHASE 3: FIXTURE DESIGN (1 DAY)
│  │  ├─ Output directory: tests/package_export/fixtures/
│  │  ├─ Test fixtures (8 total):
│  │  │  ├─ valid_manifest.yaml → MANIFEST_LOADED
│  │  │  ├─ malformed_yaml.yaml → MANIFEST_PARSE_ERROR
│  │  │  ├─ non_object_root.yaml → MANIFEST_SCHEMA_UNSUPPORTED
│  │  │  ├─ missing_instructions.yaml → MANIFEST_SCHEMA_UNSUPPORTED
│  │  │  ├─ duplicate_entry_id.yaml → MANIFEST_DUPLICATE_ENTRY_ID
│  │  │  ├─ unsupported_version.yaml → MANIFEST_VERSION_UNSUPPORTED
│  │  │  ├─ unknown_field.yaml → MANIFEST_SCHEMA_UNSUPPORTED
│  │  │  └─ source_sha_mismatch.yaml → MANIFEST_STALE_SOURCE
│  │  ├─ Configuration: tests/package_export/conftest.py
│  │  └─ Status: AUTHORIZED
│  │
│  ├─ PHASE 4: TEST SUITE (1 DAY)
│  │  ├─ Output files:
│  │  │  ├─ tests/package_export/test_manifest_load.py
│  │  │  ├─ tests/package_export/test_determinism.py
│  │  │  └─ tests/package_export/test_evidence_binding.py
│  │  ├─ Test coverage:
│  │  │  ├─ Happy path: valid manifest loads correctly
│  │  │  ├─ Error handling: all 7 reason codes triggered
│  │  │  ├─ Determinism: identical digest across runs
│  │  │  ├─ Evidence binding: all fields preserved
│  │  │  └─ Entry sorting: stable semantic inventory
│  │  ├─ Validation gate: ALL_TESTS_MUST_PASS
│  │  └─ Status: AUTHORIZED
│  │
│  ├─ PHASE 5: INTEGRATION (0.5 DAY)
│  │  ├─ Output files:
│  │  │  ├─ core/node-architect/node-catalog/package_export/package-manifest-load.node.json
│  │  │  ├─ core/node-architect/node-instructions/package_export/package-manifest-load.node-instruction.yaml
│  │  │  └─ .gwc/tasks/SCRUM-229/node-runtime/<run-id>/<node-id>/node-*.json
│  │  ├─ Integration tasks:
│  │  │  ├─ Bind loader to G2_EXECUTION gate
│  │  │  ├─ Define evidence contract and next-route decision
│  │  │  ├─ Record execution start/decision/result in ledger
│  │  │  └─ Prepare transition to G3_PR
│  │  └─ Status: AUTHORIZED
│  │
│  └─ Total effort: 5.5 days
│
├─ STEP 4: VALIDATION AND READBACK
│  ├─ All tests pass (pytest exit code = 0)
│  ├─ Determinism verified (same manifest = same digest)
│  ├─ Evidence binding validated (all fields present)
│  ├─ CI checks pass (lint, validate-instructions, tests)
│  ├─ Diff readback confirms scoped changes only
│  └─ Status: MANDATORY BEFORE TRANSITION
│
├─ STEP 5: NODE EXECUTION
│  ├─ Route: g2-resolve-execution-node
│  ├─ Nodes executed:
│  │  ├─ gate_authority.gate-state-resolution
│  │  ├─ repo_delivery.scoped-file-write
│  │  ├─ repo_delivery.diff-readback
│  │  └─ gate_authority.gate-transition-decision
│  ├─ Evidence recording: AUTOMATIC
│  └─ Next gate transition: G3_PR (Draft PR)
│
└─ COMMAND STATUS: APPROVED
```

---

## APPROVAL VERIFICATION CHECKLIST

- ✅ G0 Context Snapshot created (.gwc/tasks/SCRUM-229/g0/context-snapshot.yaml)
- ✅ G1 Intake Brief created (.gwc/tasks/SCRUM-229/g1/intake/g1-intake-brief.yaml)
- ✅ G1 Preflight Report completed (readiness: READY_FOR_G1_BRAINSTORMING)
- ✅ G1 Brainstorming Options analyzed (3 options evaluated)
- ✅ G1 Decision Record finalized (option_a selected, 5.5-day estimate)
- ✅ G2 Execution Envelope created (23 files authorized for write)
- ✅ G2 Approval Certificate issued (certificate_id: SCRUM-229-G2-APPROVAL-20260803-001)
- ✅ Jira issue SCRUM-229 claimed (AI Agent: GitHub Copilot, Claimed At: 2026-08-03T00:36:01+0700)
- ✅ Protected base SHA verified (848d0356bf003cf68f9f9c6a31b293914f2f7a00)
- ✅ Node identity confirmed (family=package_export, id=package-manifest-load)
- ✅ Target maturity verified (M2 → M4_DETERMINISTIC)
- ✅ All governance contracts read and approved
- ✅ Implementation approach approved (Pure Python Pydantic + YAML)
- ✅ Effort estimate accepted (5.5 days)
- ✅ All acceptance criteria mapped to implementation phases
- ✅ Authority fields verified (all grant flags = false, no escalation)

---

## BOUNDARY ENFORCEMENT

**Approved scopes (23 files):**

- Schemas: 2 files
- Implementation: 5 files
- Tests: 8 files
- Node definitions: 2 files
- Evidence ledger: 6 files

**Excluded operations:**

- ❌ direct_main_push
- ❌ merge
- ❌ force_push
- ❌ deploy
- ❌ release
- ❌ package_publish
- ❌ target_file_mutation
- ❌ schema_version_bump
- ❌ production_data_change
- ❌ branch_deletion

**Authority constraints:**

- author_grant_g2: **false** (gate-only control)
- author_grant_g3: **false**
- author_grant_g4: **false**
- author_grant_g5: **false**
- author_grant_g6: **false**
- node_authority_escalation_blocked: **true**
- mode_bypass_check: **PASS**

---

## NEXT ACTIONS

1. **Create isolated worktree** from protected base 848d0356bf003cf68f9f9c6a31b293914f2f7a00
2. **Create feature branch** `feature/scrum-229-package-manifest-load`
3. **Implement 5 phases** following the specification above
4. **Run all tests** and verify passing (ALL_TESTS_MUST_PASS)
5. **Verify determinism** (identical digest generation across runs)
6. **Perform diff readback** to confirm scoped changes only
7. **Trigger G2 node execution** (automatic via gate-transition-decision)
8. **Transition to G3_PR** upon successful completion

---

## VALIDITY

**Issued:** 2026-08-03T00:51:00+0700  
**Expires:** 2026-08-04T00:51:00+0700  
**Authority:** GitHub Copilot (Gate Authority, G2_EXECUTION)  
**Certificate ID:** SCRUM-229-G2-APPROVAL-20260803-001  
**Status:** VALID AND APPROVED FOR IMMEDIATE EXECUTION

---

## DEFINITION OF DONE (DOD)

The G2 execution is complete when:

- [ ] All 5 implementation phases completed
- [ ] Schema definition created with Pydantic models and JSON schema
- [ ] Loader, validator, digest generator implemented
- [ ] All 8 test fixtures created with expected outcomes
- [ ] All tests pass (pytest exit code 0)
- [ ] Determinism verified: same manifest → identical digest
- [ ] Evidence binding validated: all fields captured correctly
- [ ] Entry sorting by stable ID verified
- [ ] Node descriptor and instruction created and registered
- [ ] Node-runtime ledger populated (start/decision/result/next-route)
- [ ] CI validation passed (lint, tests, validate-instructions)
- [ ] No scope drift confirmed
- [ ] Diff readback shows scoped changes only
- [ ] Ready for G3_PR transition

---

**Command issued by:** GitHub Copilot  
**Authority level:** Gate Authority (G2_EXECUTION)  
**Execution mode:** local_agent  
**Status:** APPROVED FOR IMMEDIATE EXECUTION
