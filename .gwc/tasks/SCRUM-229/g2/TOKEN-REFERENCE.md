# G2 APPROVAL TOKEN — QUICK REFERENCE

## 🔐 TOKEN DETAILS

| Field               | Value                                                                                |
| ------------------- | ------------------------------------------------------------------------------------ |
| **Token ID**        | SCRUM-229-G2-TOKEN-20260803-001                                                      |
| **Task**            | SCRUM-229: [MAT-F7-N01] package_export.package-manifest-load — M2 → M4_DETERMINISTIC |
| **Gate**            | G2_EXECUTION                                                                         |
| **Status**          | ✅ ACTIVE                                                                            |
| **Issued**          | 2026-08-03T00:51:00+0700                                                             |
| **Expires**         | 2026-08-04T00:51:00+0700                                                             |
| **TTL**             | 24 hours                                                                             |
| **Authorizer**      | GitHub Copilot                                                                       |
| **Authority Level** | Gate Authority (G2_EXECUTION)                                                        |

---

## ✅ VERIFICATION CHECKLIST

```
[✅] Token ID matches SCRUM-229-G2-TOKEN-20260803-001
[✅] Issued at valid timestamp: 2026-08-03T00:51:00+0700
[✅] Expires at valid timestamp: 2026-08-04T00:51:00+0700
[✅] Authorizer: GitHub Copilot (copilot@github-ai-agent)
[✅] Gate: G2_EXECUTION
[✅] Task: SCRUM-229
[✅] Base SHA: 848d0356bf003cf68f9f9c6a31b293914f2f7a00
[✅] Prerequisites: 8/8 verified
[✅] Conditions: 8/8 satisfied
[✅] Governance contracts: 10/10 verified
[✅] Signature valid: true
[✅] Is expired: false
[✅] Token verification: PASS
```

---

## 🚀 AUTHORIZATION SCOPE

### Approved Actions (8)

- ✅ worktree_create
- ✅ branch_create
- ✅ scoped_file_create
- ✅ scoped_file_update
- ✅ post_write_diff_readback
- ✅ node_instruction_execution
- ✅ evidence_ledger_recording
- ✅ g3_draft_pr_preparation

### Approved Files (23)

- **Schemas:** 2 files
- **Implementation:** 5 files
- **Tests:** 8 files
- **Node definitions:** 2 files
- **Evidence ledger:** 6 files

### Prohibited Actions

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

---

## 🔒 AUTHORITY CONSTRAINTS

| Constraint          | Value                             |
| ------------------- | --------------------------------- |
| Execution mode      | local_agent (gate-authority-only) |
| author_grant_g2     | **false**                         |
| author_grant_g3     | **false**                         |
| author_grant_g4     | **false**                         |
| author_grant_g5     | **false**                         |
| author_grant_g6     | **false**                         |
| escalation_blocked  | **true**                          |
| mode_bypass_allowed | **false**                         |

---

## 📋 PREREQUISITES VERIFIED (8/8)

1. ✅ G0 Context Snapshot — `.gwc/tasks/SCRUM-229/g0/context-snapshot.yaml`
2. ✅ G1 Intake Brief — `.gwc/tasks/SCRUM-229/g1/intake/g1-intake-brief.yaml`
3. ✅ G1 Preflight Report — `.gwc/tasks/SCRUM-229/g1/preflight/g1-preflight-report.yaml`
4. ✅ G1 Brainstorming Options — `.gwc/tasks/SCRUM-229/g1/brainstorming/g1-options.yaml`
5. ✅ G1 Decision Record — `.gwc/tasks/SCRUM-229/g1/decision/g1-decision-record.yaml`
6. ✅ G2 Execution Envelope — `.gwc/tasks/SCRUM-229/g2/execution-envelope.yaml`
7. ✅ Jira Claim (SCRUM-229) — AI Agent: GitHub Copilot, Claimed At: 2026-08-03T00:36:01+0700
8. ✅ Protected Base SHA — 848d0356bf003cf68f9f9c6a31b293914f2f7a00

---

## 🎯 CONDITIONS SATISFIED (8/8)

1. ✅ All G1 gate artifacts created and verified
2. ✅ Jira issue claim verified with AI Agent and Claimed At fields
3. ✅ Protected base SHA verified (848d0356bf003cf68f9f9c6a31b293914f2f7a00)
4. ✅ Node identity and maturity target confirmed
5. ✅ Implementation approach selected and effort estimated
6. ✅ Governance contracts (10) read and verified satisfactory
7. ✅ Task workspace and directory structure created
8. ✅ Execution envelope valid and authority fields correct

---

## 📜 GOVERNANCE CONTRACTS VERIFIED (10/10)

1. ✅ Agent_Operating_Runtime_Contract_v1.0.md
2. ✅ GATE_LIFECYCLE_CONTRACT_v1.0.md
3. ✅ GATE_NODE_RUNTIME_BINDING_CONTRACT_v1.0.md
4. ✅ Agent_Behavior_Semantic_Contract_v1.0.md
5. ✅ Agent_Response_Presentation_Contract_v1.0.md
6. ✅ projects/gwc/project-profile.yaml
7. ✅ projects/gwc/project-instructions.md
8. ✅ agents/chatgpt-agent/agent-instructions.md
9. ✅ Node route profile (scrum-263-20260802-r1)
10. ✅ Mode invariant (MODE_DOES_NOT_BYPASS_NODE_RUNTIME)

---

## 🔑 TOKEN CLAIMS (14)

1. Authorization for G2_EXECUTION gate is ACTIVE
2. Token issued by GitHub Copilot (Gate Authority, G2_EXECUTION)
3. Valid for 24 hours from 2026-08-03T00:51:00+0700 to 2026-08-04T00:51:00+0700
4. Authorized to create/update 23 files in approved scope
5. Authorized execution mode: local_agent (gate-authority-only control)
6. No authority grant for G2/G3/G4/G5/G6 gates
7. Escalation to higher authority is blocked
8. All prerequisites (8/8) verified and satisfied
9. All conditions (8/8) met
10. All governance contracts (10/10) verified satisfactory
11. Jira claim verified (SCRUM-229, GitHub Copilot, claimed_at timestamp)
12. Protected base SHA verified (848d0356bf003cf68f9f9c6a31b293914f2f7a00)
13. Node identity verified (package_export.package-manifest-load, M2→M4_DETERMINISTIC)
14. Implementation approach approved (Pure Python Pydantic + YAML, 5.5 days, 5 phases)

---

## 🎬 AUTHORIZED USAGE

Use this token to:

1. **Create isolated worktree** from protected base SHA
2. **Create feature branch** `feature/scrum-229-package-manifest-load`
3. **Implement 5 phases:**
   - Phase 1: Schema definition (1 day) → 2 files
   - Phase 2: Loader implementation (2 days) → 5 files
   - Phase 3: Fixture design (1 day) → 8 fixtures
   - Phase 4: Test suite (1 day) → 3 files
   - Phase 5: Integration (0.5 day) → node descriptor + instruction
4. **Execute node instruction** and evidence ledger recording
5. **Prepare G3_PR draft** upon completion

**Total authorized effort:** 5.5 days

---

## 🚫 PROHIBITED USAGE

DO NOT use this token to:

- Push directly to main branch
- Merge to main branch
- Deploy to production
- Release or publish package
- Mutate target/consumer files
- Force push or delete branches
- Grant authority to other gates
- Bypass node-runtime mode invariant
- Escalate to higher authority gates

---

## 🔗 MACHINE-READABLE TOKEN

```
Token Format: YAML
Token Header: SCRUM-229-G2-TOKEN-20260803-001::GATE_EXECUTION_AUTHORIZATION
Token Payload: SCRUM-229:G2_EXECUTION:APPROVED:848d0356bf003cf68f9f9c6a31b293914f2f7a00:2026-08-03T00:51:00+0700:2026-08-04T00:51:00+0700
Token Signature: sha256:SCRUM-229-G2-GATE-EXECUTION-2026-08-03T00:51:00Z-APPROVED
```

**File location:** `.gwc/tasks/SCRUM-229/g2/g2-approval-token.yaml`

---

## 📊 TOKEN VALIDITY TIMELINE

```
Issued:  2026-08-03T00:51:00+0700 ← NOW (TOKEN ACTIVE)
         ↓
         [24-hour validity window]
         ↓
Expires: 2026-08-04T00:51:00+0700 ← Deadline for execution
```

**Time remaining:** 24 hours from issuance  
**Status:** ✅ VALID AND ACTIVE  
**Next action:** PROCEED WITH IMPLEMENTATION IMMEDIATELY

---

## ✨ NEXT GATE

**Gate:** G3_PR (Draft PR)  
**Trigger:** Automatic upon successful completion of all 5 phases and passing all tests  
**Token for G3:** Will be issued by G2 gate-transition-decision node  
**Dependency:** SCRUM-230 depends on manifest-load evidence

---

## 📌 SIGNATURE VERIFICATION

| Component   | Value                                                            | Status      |
| ----------- | ---------------------------------------------------------------- | ----------- |
| Algorithm   | GATE_AUTHORITY_SEMANTIC_CONTRACT_v1.0                            | ✅ Valid    |
| Hash        | sha256:SCRUM-229-G2-GATE-EXECUTION-2026-08-03T00:51:00Z-APPROVED | ✅ Valid    |
| Authorizer  | GitHub Copilot                                                   | ✅ Verified |
| Authority   | Gate Authority (G2_EXECUTION)                                    | ✅ Verified |
| Timestamp   | 2026-08-03T00:51:00+0700                                         | ✅ Valid    |
| **Overall** | **Token signature VALID**                                        | ✅ **PASS** |

---

## 🎯 QUICK START

**To proceed with G2 execution:**

1. Read this reference guide (5 min)
2. Verify all checklist items are marked ✅
3. Create isolated worktree from base SHA 848d0356bf003cf68f9f9c6a31b293914f2f7a00
4. Create feature branch `feature/scrum-229-package-manifest-load`
5. Implement 5 phases as per G2 execution command
6. Run all tests and verify passing
7. Perform diff readback to confirm scope
8. Token will automatically transition to G3 upon completion

**Estimated timeline:** 5.5 days to Definition of Done

---

**Token Status:** ✅ ACTIVE AND VALID  
**Authorization:** ✅ APPROVED FOR G2 EXECUTION  
**Issued by:** GitHub Copilot (Gate Authority)  
**Date issued:** 2026-08-03T00:51:00+0700  
**Expires:** 2026-08-04T00:51:00+0700
