# Rev 10 Plan Correction Delta

**Task:** CP-20261004-001
**Target:** fix/SCRUM-781-q0-canonical
**Branch:** auto/GWC-v2-PlanFix-SCRUM781-na81-20261004
**Kernel:** d16d587 (SCRUM-668)
**Baseline:** 414002f (noop HEAD)
**Risk class:** R1
**Scope:** Plan correction only — no kernel code changes

---

## Delta Summary

```
10 ADD | 3 MERGE | 3 REJECT | 4 VERIFY_AND_REUSE
```

---

## 10 ADD — New Tasks

| ID | Title | Phase | Rationale |
|---|---|---|---|
| ADD-01 | Kernel Inheritance Baseline | Pre-R0 | Establish kernel inheritance from d16d587 before any migration task |
| ADD-02 | TargetContract/ContextSnapshot per Child Run | R0 | G0 must bind full TargetContract fields, not just repo/branch/SHA |
| ADD-03 | RunStateStorePort reconnection | R0 | Migration durable evidence must map to RunStateStorePort, not create second source |
| ADD-04 | Recursive ChildRun semantic regression | R0 | Implementation tasks ≠ Universal ChildRun contract proof |
| ADD-05 | RunControlPort transport-neutral conformance | R0 | CLI/API/A2A/mailbox adapter invariance must be verified |
| ADD-06 | Cross-run dependency + freshness | R1 | Phase-SHA chaining ≠ freshness expiry, stale handoff rejection |
| ADD-07 | Migration receipt → canonical evidence mapping | R1 | Checkpoint/lane_event/integration_receipt must map to RunEventLedger/ExecutionReceipt/ClosureReceipt |
| ADD-08 | L0-L5 test traceability | R2 | Static/schema → unit → component → integration → multi-domain E2E → adversarial |
| ADD-09 | Full multi-domain + adversarial R8 certification | R8 | Non-software recursive Run, research/document Run, external/observed-state Run, fresh-controller recovery |
| ADD-10 | Pre-R0 component/RACI ownership binding | Pre-R0 | Component owners frozen before parallel coding |

## 3 MERGE — Merge Existing Tasks

| ID | Action | Target |
|---|---|---|
| MERGE-01 | Merge R5 Rescue/Research verticals into R5 definition | R5 |
| MERGE-02 | Merge R6/R7/R8 blank placeholder rows with actual task content | R6-R8 |
| MERGE-03 | Merge Post-effect evidence plane into EvidencePort canonical model | R3 |

## 3 REJECT — Reject Tasks

| ID | Task | Reason |
|---|---|---|
| REJECT-01 | Second migration evidence system parallel to RunStateStorePort | DUPLICATE — creates competing semantic truth |
| REJECT-02 | Lane-specific lifecycle semantics as new Universal position | WRONG_PROMOTION — migration control ≠ lifecycle |
| REJECT-03 | Unbounded retry without CAS/lease/fencing | DANGEROUS — violates idempotency invariant |

## 4 VERIFY_AND_REUSE — Verify and Reuse Existing Kernel Code

| ID | Module | Action |
|---|---|---|
| VERIFY-01 | universal_run_plan.py | VERIFY_AND_REUSE — no rewrite, regression test only |
| VERIFY-02 | universal_run_certification.py | VERIFY_AND_REUSE — no rewrite, regression test only |
| VERIFY-03 | universal_run_authority.py | VERIFY_AND_REUSE — no rewrite, regression test only |
| VERIFY-04 | semantic_lifecycle.py | VERIFY_AND_REUSE — no rewrite, regression test only |

---

## Readiness

| Gate | Status | Blockers |
|---|---|---|
| PRE_R0 | NO | Kernel inheritance baseline, TargetContract binding, RunStateStorePort reconnection, RACI ownership, scope hash |
| R0 | NO | All PRE_R0 + RunControlPort conformance, ChildRun regression, cross-run freshness, evidence mapping, L0-L5 |
| R1+ | NO | All R0 + OBSERVED_STATE regression, R5 Rescue/Research undefined, R6/R7/R8 blank |
| G2 | BLOCKED | Scope hash unverified (now RESOLVED: `6bc200e6bff4add9`) |
