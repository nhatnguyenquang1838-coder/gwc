# G4 APPROVAL COMMAND — SCRUM-229

**Task:** [MAT-F7-N01] package_export.package-manifest-load — M2 → M4_DETERMINISTIC  
**Gate:** G4_APPROVAL  
**Review Type:** Human Review and Approval  
**Issued:** 2026-08-03T00:51:00+0700  
**Expires:** 2026-08-10T00:51:00+0700 (7 days)  
**Authority:** G4_APPROVAL Gate Authority (Human Reviewer)

---

## APPROVAL COMMAND SUMMARY

```
HUMAN REVIEW REQUIRED FOR SCRUM-229 DRAFT PR
│
├─ PR Title: [SCRUM-229] Implement package_export.package-manifest-load at M4_DETERMINISTIC
├─ PR Base: main (SHA: 848d0356bf003cf68f9f9c6a31b293914f2f7a00)
├─ PR Target: feature/scrum-229-package-manifest-load
├─ PR Files: 23 (scoped)
│
├─ REVIEW SCOPE: Verify implementation correctness and completeness
├─ DECISION REQUIRED: Approve, Request Changes, or Reject
├─ ESCALATION AUTHORITY: Yes (human reviewer has approval authority)
│
├─ UPON APPROVAL: Automatic transition to G5_MERGE
├─ UPON REQUEST CHANGES: Return to implementation (if needed)
├─ UPON REJECTION: Remain at G4 for reconsideration
│
└─ COMMAND STATUS: READY FOR HUMAN REVIEW
```

---

## 📋 REVIEWER CHECKLIST

### Pre-Review Verification (Must Pass Before Review)

- [ ] PR created from base SHA 848d0356bf003cf68f9f9c6a31b293914f2f7a00
- [ ] PR base branch is main
- [ ] PR target branch is feature/scrum-229-package-manifest-load
- [ ] PR contains exactly 23 files (no more, no less)
- [ ] PR title: [SCRUM-229] Implement package_export.package-manifest-load at M4_DETERMINISTIC
- [ ] PR labels: node-architect, package-export, M4-deterministic, scrum-229
- [ ] PR linked to SCRUM-229 task
- [ ] All CI checks passing (lint, tests, validate-instructions)
- [ ] All tests passing (pytest exit code 0)
- [ ] Determinism verified (same manifest = same digest)

### Implementation Review

#### Phase 1: Schema Definition Review

**Files to review:**

- `schemas/node-architect/package-export/package-manifest.schema.yaml`
- `schemas/node-architect/package-export/package-manifest.schema.json`

**Review criteria:**

- [ ] Root object schema defined with required fields (version, id, entries)
- [ ] Version field supports semantic versioning
- [ ] Entries field is a list with mandatory id, name, type
- [ ] Evidence binding fields present: source_repo, source_ref, source_sha, task_id
- [ ] Unknown fields explicitly rejected (forbid extra)
- [ ] Schema is valid YAML and JSON
- [ ] JSON schema matches YAML schema semantically

**Questions to answer:**

- Does the schema correctly define the manifest format?
- Are all required fields present and correctly typed?
- Is evidence binding complete?
- Are there any missing validations?

#### Phase 2: Loader Implementation Review

**Files to review:**

- `tools/node_architect/package_export/__init__.py`
- `tools/node_architect/package_export/models.py`
- `tools/node_architect/package_export/loader.py`
- `tools/node_architect/package_export/validator.py`
- `tools/node_architect/package_export/digest.py`

**Review criteria:**

- [ ] Pydantic models correctly implement schema (models.py)
- [ ] YAML parsing handles edge cases and errors gracefully (loader.py)
- [ ] Custom validators enforce business logic (validator.py):
  - [ ] Duplicate ID detection
  - [ ] Version compatibility checking
  - [ ] Source binding verification
- [ ] Deterministic digest generation using json.dumps(sort_keys=True) (digest.py)
- [ ] Preserves declared instruction order in provenance field
- [ ] Produces canonical semantic inventory sorted by stable entry ID
- [ ] Supports exact source SHA, package path, repository, and source ref bindings
- [ ] Emits stable reason codes (7 codes defined)
- [ ] No external dependencies beyond Pydantic v2 and PyYAML
- [ ] Type hints complete and accurate

**Questions to answer:**

- Is the implementation robust against invalid input?
- Is determinism guaranteed across runs?
- Does evidence binding capture all required information?
- Are error messages clear and actionable?
- Is the code maintainable and well-documented?

#### Phase 3: Fixture Design Review

**Files to review:**

- `tests/package_export/fixtures/valid_manifest.yaml`
- `tests/package_export/fixtures/malformed_yaml.yaml`
- `tests/package_export/fixtures/non_object_root.yaml`
- `tests/package_export/fixtures/missing_instructions.yaml`
- `tests/package_export/fixtures/duplicate_entry_id.yaml`
- `tests/package_export/fixtures/unsupported_version.yaml`
- `tests/package_export/fixtures/unknown_field.yaml`
- `tests/package_export/fixtures/source_sha_mismatch.yaml`
- `tests/package_export/conftest.py`

**Review criteria:**

- [ ] 8 fixtures cover all error modes
- [ ] Each fixture has clear documentation of expected outcome
- [ ] Valid manifest fixture is well-formed and complete
- [ ] Malformed YAML fixture triggers parse error
- [ ] Non-object root fixture triggers schema error
- [ ] Missing instructions field triggers schema error
- [ ] Duplicate entry ID detected and reported
- [ ] Unsupported version detected and reported
- [ ] Unknown top-level field detected and rejected
- [ ] Source SHA mismatch detected and reported
- [ ] conftest.py provides helper functions for test setup

**Questions to answer:**

- Do the fixtures cover all acceptance criteria?
- Are error scenarios well-represented?
- Are fixture names clear and descriptive?
- Is test data realistic and appropriate?

#### Phase 4: Test Suite Review

**Files to review:**

- `tests/package_export/test_manifest_load.py`
- `tests/package_export/test_determinism.py`
- `tests/package_export/test_evidence_binding.py`

**Review criteria:**

- [ ] test_manifest_load.py covers happy path and error handling
- [ ] test_determinism.py verifies byte-for-byte consistency across runs
- [ ] test_evidence_binding.py validates all required fields are captured
- [ ] All 6 acceptance criteria have test coverage
- [ ] All 7 reason codes are triggered in tests
- [ ] Entry sorting order is verified
- [ ] Tests use appropriate assertions and error checks
- [ ] Test names are descriptive and clear
- [ ] No hardcoded paths or environment dependencies
- [ ] All tests pass with exit code 0

**Questions to answer:**

- Is test coverage comprehensive?
- Are tests independent and repeatable?
- Do tests validate both happy path and error cases?
- Is determinism verified properly?
- Is evidence binding validated completely?

#### Phase 5: Integration Review

**Files to review:**

- `core/node-architect/node-catalog/package_export/package-manifest-load.node.json`
- `core/node-architect/node-instructions/package_export/package-manifest-load.node-instruction.yaml`
- `.gwc/tasks/SCRUM-229/node-runtime/<run-id>/<node-id>/node-result.json`

**Review criteria:**

- [ ] Node descriptor correctly binds loader to G2_EXECUTION gate
- [ ] Node descriptor defines evidence contract properly
- [ ] Node instruction specifies next-route decision logic
- [ ] Evidence recording matches contract
- [ ] Node-runtime directory structure correct
- [ ] All required fields present in node-result.json
- [ ] Evidence is deterministic and reproducible
- [ ] Next-route decision points to G3_PR correctly

**Questions to answer:**

- Is the node descriptor valid and complete?
- Does the evidence contract match implementation?
- Is the next-route decision logic correct?
- Are all integration points properly defined?

### Acceptance Criteria Verification

- [ ] **AC1 (Typed Binding):** Explicit Pydantic model fields for task, repo, path, ref, SHA, version, digest
- [ ] **AC2 (Fixture Coverage):** 8 comprehensive fixtures covering all error modes
- [ ] **AC3 (Determinism):** Identical digest generation verified across multiple runs
- [ ] **AC4 (Blocked/Fail):** Validator rejects missing/ambiguous input before inventory generation
- [ ] **AC5 (Descriptor/Gates):** Node descriptor and instruction define evidence boundaries correctly
- [ ] **AC6 (Tests Pass):** All tests passing with pytest exit code 0

### Code Quality Review

- [ ] Code follows project style guidelines
- [ ] Type hints are complete and accurate
- [ ] Error handling is comprehensive
- [ ] Edge cases are considered and handled
- [ ] Documentation is clear and complete
- [ ] No technical debt introduced
- [ ] Performance is acceptable
- [ ] Dependencies are minimal and justified

### Security Review

- [ ] No hardcoded credentials or secrets
- [ ] Input validation prevents injection attacks
- [ ] File operations are safe (no path traversal)
- [ ] YAML parsing is safe (no arbitrary code execution)
- [ ] No unsafe external library calls

### Scope Review

- [ ] Only 23 approved files are included
- [ ] No files added outside approved scope
- [ ] No modifications to unrelated code
- [ ] No schema version changes
- [ ] No package publishing or releasing
- [ ] Changes are atomic and focused on node implementation

---

## 📊 APPROVAL DECISION MATRIX

| Review Result          | Action                | Next Step                                                  |
| ---------------------- | --------------------- | ---------------------------------------------------------- |
| ✅ **Approved**        | Approve PR            | Automatic transition to G5_MERGE                           |
| 🔄 **Request Changes** | Request changes in PR | Update PR, return to review, or implementation (if needed) |
| ❌ **Reject**          | Reject PR             | Remain at G4, reconsider, or return to implementation      |

---

## 🚀 APPROVAL PATH

### Scenario 1: APPROVED ✅

```
Reviewer: ✅ All checks pass, code quality excellent
  ↓
Reviewer: Approve PR
  ↓
G4 Gate: Record approval decision
  ↓
Automatic transition to G5_MERGE
  ↓
G5 Gate: Merge to main
  ↓
G6 Gate: Release and document maturity transition
```

### Scenario 2: REQUEST CHANGES 🔄

```
Reviewer: Some issues found, minor changes requested
  ↓
Reviewer: Request changes in PR
  ↓
Developer: Update PR with requested changes
  ↓
Re-run tests and validation
  ↓
Return to G4 for re-review
  ↓
(Loop until approved or rejected)
```

### Scenario 3: REJECTED ❌

```
Reviewer: Major issues found, PR cannot proceed
  ↓
Reviewer: Reject PR with explanation
  ↓
G4 Gate: Record rejection decision
  ↓
Return to implementation (SCRUM-229 remains in progress)
  ↓
(Requires new iteration or significant rework)
```

---

## 🔐 APPROVAL AUTHORITY

| Authority               | Power                                 |
| ----------------------- | ------------------------------------- |
| **Human Reviewer (G4)** | ✅ Approve or Request Changes         |
| **GitHub Copilot**      | 🔍 Optional: Auto-review code quality |
| **System (G5)**         | ⏳ Awaits G4 decision for merge       |

**Escalation:** Human reviewer has full authority to approve, request changes, or reject.

---

## ⏰ TIMELINE

| Phase                | Duration        | Status                        |
| -------------------- | --------------- | ----------------------------- |
| G0-G3 Complete       | —               | ✅ DONE                       |
| G2 Execution         | 5.5 days        | ⏳ In Progress (or Completed) |
| G3 Draft PR Assembly | < 1 hour        | ✅ Ready upon G2 completion   |
| **G4 Human Review**  | **24-72 hours** | **⏳ CURRENT PHASE**          |
| G5 Merge             | 1-2 hours       | ⏳ Awaits G4 approval         |
| G6 Release           | < 1 day         | ⏳ Awaits G5 completion       |

**Review window:** 7 days (expires 2026-08-10T00:51:00+0700)

---

## 🎯 APPROVAL CONDITIONS

### Must-Pass Conditions

✅ All CI checks passing  
✅ All tests passing  
✅ Determinism verified  
✅ 23 files exactly (no more, no less)  
✅ PR base is correct (main, 848d0356bf003cf68f9f9c6a31b293914f2f7a00)  
✅ PR metadata correct (title, labels, linked to SCRUM-229)  
✅ No scope drift

### Approval Criteria

✅ Code quality acceptable  
✅ Implementation approach sound  
✅ All acceptance criteria met  
✅ Evidence binding complete  
✅ Determinism proven  
✅ Tests comprehensive  
✅ Documentation adequate

---

## 📝 APPROVAL DECISION TEMPLATE

**When Ready to Approve:**

```
## ✅ APPROVED

**Reviewer:** [Name]
**Approval Date:** [Date]
**Approval Time:** [Time]
**Decision:** APPROVED FOR MERGE

**Rationale:**
- All acceptance criteria met
- Code quality excellent
- Tests comprehensive and passing
- Determinism verified
- Evidence binding complete
- Implementation approach sound

**Comments:**
[Optional feedback or observations]

**Approved By:** [Reviewer Name/Authority]
```

**When Requesting Changes:**

```
## 🔄 REQUEST CHANGES

**Reviewer:** [Name]
**Date:** [Date]
**Decision:** REQUEST CHANGES

**Required Changes:**
1. [Issue 1]
2. [Issue 2]
3. [Issue 3]

**Notes:**
[Explanation of issues and expected fixes]

**Next Steps:**
- Make requested changes
- Re-run tests
- Return for re-review

**Requested By:** [Reviewer Name/Authority]
```

**When Rejecting:**

```
## ❌ REJECTED

**Reviewer:** [Name]
**Date:** [Date]
**Decision:** REJECTED

**Rejection Reason:**
[Clear explanation of why PR cannot proceed]

**Required Actions:**
1. [Major issue 1]
2. [Major issue 2]
3. [Major issue 3]

**Recommendation:**
[Path forward - new iteration, rework, etc.]

**Rejected By:** [Reviewer Name/Authority]
```

---

## 🔗 NEXT GATE (G5)

**Gate:** G5_MERGE  
**When triggered:** Upon G4 approval  
**Responsibility:** Merge to main and validate integration  
**Authority:** System (automated merge gate)  
**Requirements:** All G4 approval conditions met

---

## 📞 CONTACT & ESCALATION

**Questions or Issues?**

- **Task Lead:** SCRUM-229 in Jira
- **G4 Authority:** Human reviewer assigned
- **Escalation:** Contact GWC governance team if approval blocked

---

## ✨ FINAL CHECKLIST

**Before Starting Review:**

- [ ] PR exists and is accessible
- [ ] All CI checks have run successfully
- [ ] Can access all 23 PR files
- [ ] Have read G1 decision record for context
- [ ] Have reviewed implementation approach and estimate

**During Review:**

- [ ] Verify pre-review checklist items (must all pass)
- [ ] Review each of 5 phases (schema, loader, fixtures, tests, integration)
- [ ] Verify all 6 acceptance criteria
- [ ] Check code quality and security
- [ ] Verify scope (23 files exactly)

**After Review:**

- [ ] Complete approval decision template
- [ ] Post decision to PR or task
- [ ] If approved: Transition to G5_MERGE (automatic)
- [ ] If changes requested: Notify developer and wait for update
- [ ] If rejected: Document reasoning for future reference

---

## 🎬 HOW TO PROCEED

1. **Receive PR notification** when Draft PR is created by G3 gate
2. **Review this checklist** to understand what to examine
3. **Review the 23 files** using checklist items above
4. **Verify all acceptance criteria** are met
5. **Make approval decision** (approve, request changes, or reject)
6. **Post decision** to PR/task using template above
7. **Upon approval:** System automatically transitions to G5_MERGE

---

**Command issued by:** GitHub Copilot (Gate Authority, G2_EXECUTION)  
**For review by:** Human Reviewer (G4_APPROVAL Authority)  
**Decision required by:** 2026-08-10T00:51:00+0700 (7-day window)  
**Status:** ✅ READY FOR HUMAN REVIEW
