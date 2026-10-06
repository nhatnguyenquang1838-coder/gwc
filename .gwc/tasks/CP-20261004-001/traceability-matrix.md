# Traceability Matrix — GWC v2 Migration Reconciliation Review

**Kernel:** d16d587 | **Baseline:** 414002f (noop) | **Review:** 4 unanimous → PLAN_ALIGNED_WITH_REQUIRED_CHANGES

## Requirement Matrix

| Original requirement | Original source | Existing implementation state | Current migration phase/task | Coverage | Gap / correction |
|---|---|---|---|---|---|
| Run identity | Contract Freeze | Kernel run-id generation | Pre-R0 P0-01 | PARTIAL | Identity must include consumer/parent binding |
| ContextSnapshot | Contract Freeze | P0-02 session task | Pre-R0 | PARTIAL | Missing source/context, constraints, authority boundary |
| TargetContract | Contract Freeze | Not explicitly bound | ADD-02 | MISSING | G0 must bind full TargetContract revision fields |
| Universal lifecycle G0-G6 | Contract Freeze | GWC Universal Runtime v2 | All phases | PRESERVED | Lifecycle semantics intact |
| Gate state machine | Contract Freeze | Gate resolution engine | R4 | PRESERVED | No drift |
| RuntimePlan | Contract Freeze | universal_run_plan.py | R4 | PRESERVED | VERIFY_AND_REUSE |
| RunStateStorePort | Detailed Architecture | "Durable evidence provider" | ADD-03 | MISSING | Migration evidence must map to RunStateStorePort |
| RunControlPort | Detailed Architecture | Internal registry only | ADD-05 | MISSING | CLI/API/A2A/mailbox adapter invariance unverified |
| AuthorityDecisionReceipt | Detailed Architecture | Authority boundary check | R3 | PARTIAL | Receipt format not explicitly frozen |
| Effect/readback | Detailed Architecture | Effect runner | R3 | PARTIAL | Readback must include stability check |
| Recursive Parent/Child Run | Detailed Architecture | Node execution engine | ADD-04 | MISSING | SINGLE_ACTIVE/cycle-guard/topology-budget regression |
| NodeDefinition / NodeAllocation | Detailed Architecture | Node registry | R4 | PRESERVED | No drift |
| WORK / CONTROL | Detailed Architecture | Node execution engine | R4 | PRESERVED | No drift |
| Child requirement policy | Detailed Architecture | TaskController contract | R4 | PRESERVED | No drift |
| Parent aggregation policy | Detailed Architecture | TaskController contract | R4 | PRESERVED | No drift |
| Cycle / ancestor guards | Detailed Architecture | Node execution engine | R4 | PARTIAL | No explicit regression task |
| Topology budgets | Detailed Architecture | TaskController contract | R4 | PARTIAL | Budget enforcement unverified |
| Idempotency | Detailed Architecture | CAS/lease/fencing | Pre-R0 | PRESERVED | No drift |
| Drift / replan | Detailed Architecture | Replan logic | R4 | PARTIAL | Freshness policy missing |
| Cross-Run dependencies | Contract Freeze | Phase-SHA chaining | ADD-06 | MISSING | Freshness expiry, stale handoff rejection |
| Evidence / OutputManifest | Detailed Architecture | Migration checkpoint system | ADD-07 | MISSING | Migration artifacts must map to canonical evidence |
| OBSERVED_STATE | Detailed Architecture | Observer pattern | R5 | MISSING | No regression task |
| Closure / Handoff | Detailed Architecture | Handoff protocol | R6 | PRESERVED | No drift |
| Legacy compatibility | Contract Freeze | Compatibility layer | R1 | PRESERVED | No drift |
| Package / versioning | Detailed Architecture | Distribution package | R6 | PARTIAL | Versioning not explicitly frozen |
| Multi-domain certification | Detailed Architecture | Not defined | ADD-09 | MISSING | Non-software, research, observed-state domains |
| Cutover / rollback | Contract Freeze | R8 frozen cutover | R8 | PARTIAL | Rollback procedure undefined |

---

## Missing / Underrepresented (ordered by severity)

1. **CRITICAL** — TargetContract/ContextSnapshot per Child Run (ADD-02)
2. **CRITICAL** — RunControlPort transport-neutral conformance (ADD-05)
3. **CRITICAL** — Recursive ChildRun semantic regression (ADD-04)
4. **HIGH** — RunStateStorePort mapping (ADD-03)
5. **HIGH** — Cross-run dependency freshness (ADD-06)
6. **HIGH** — Evidence model canonical mapping (ADD-07)
7. **MEDIUM** — OBSERVED_STATE/ResourceDescriptor (ADD-09)
8. **MEDIUM** — Multi-domain certification (ADD-09)
9. **MEDIUM** — L0-L5 test traceability (ADD-08)
10. **MEDIUM** — Pre-R0 RACI ownership binding (ADD-10)
