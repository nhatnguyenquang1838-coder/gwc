# G1 Design / Implementation Plan — COMMAND #189
## GENERIC Universal V2: recursive G0→G6 + inherited/derived authority + risk-based HITL/HOTL

- **Controller command:** #189 (GitHub #595 comment 6344695425), from: GPT, human-authorized DESIGN+IMPLEMENTATION.
- **Run:** scrum781-q0-fresh-20261010-r1 · **Parent gate:** UR.G2 / RUN_NOT_COMPLETE.
- **Protected main base (re-checked):** `f560db71705d89d0ded2a5efbcaeb4c7c4dafab8`.
- **Mode:** GENERIC shared-runtime work. NOT a Q0-consumer change. Separate governed parent branch/worktree required (do NOT edit shared runtime on the Q0-only branch `fix/SCRUM-781-q0-fresh-20261010-r1`).
- **Hard boundaries (unchanged):** A stays closed safe; B (real Q0 active selector/checkpoint/cursor) unapproved; no protected-main merge, deploy, production, secret, migration, destructive, G6-human-acceptance widening. HOTL = observation, not approval.

---

## 1. Canonical source map (ENHANCE, do not replace)
Live executable path (verified by integration lane):
`tools/node_architect/agent_runtime_cli.py::main` → `UniversalController.assign_current_action()` → `UniversalExecutor.execute()` → `UniversalController.consume_executor_receipt()`.
Currently ONE native assignment+receipt per invocation; recursion + authority evaluators are NOT wired in.

Existing canonical modules to enhance:
- `universal_run_kernel.py` (UNIVERSAL_PROFILE, kernel errors)
- `universal_run_lifecycle.py`, `universal_run_node.py`, `universal_run_state.py`
- `universal_run_controller.py`, `universal_run_continuation.py`, `universal_run_execution.py`
- `universal_run_authority.py` — `resolve_authority()` (lines 174–198) matches receipt→exact task_id+action; C6 orthogonal authority, C10 self-grant/stale fail-closed already enforced.
- `risk_classification.py::render_risk_classification` — R0–R3; R0/R1 `G2_AUTOMATIC_BOUNDED`, R2/R3 `G2_HUMAN_DIRECTION`.
- `derive_task_authority.py::derive_g2_authority` — manifest-based evaluator (NOT inherited ChildRun authority).
- `materialize_autonomous_preprod_run_authority.py` — strongest existing delegation analogue (codes: `AUTONOMOUS_CHILD_G2_AUTHORIZED`, `AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED`, `AUTONOMOUS_HEAD_DRIFT`, …) but pre-prod-specific, no general recursive parent→child contract.

Node catalog (enhance, route through): `core/node-catalog/gate_authority/{approval-token-generation, g2-execution-envelope-render, authority-boundary-check, blocked-action-escalation, scope-hash-calculation}.node.json`; `intake_context/risk-classification.node.json`.

Schemas already present (reuse): `run-manifest-revision` (ROOT vs CHILD; child requires parent+allocation), `node-allocation` (child instance policy, independent-boundary), `child-run-materialization-receipt` (DAG budget, SINGLE_ACTIVE, max depth, provenance, content digest), `context-snapshot` (`authority_effect_boundary.grants_authority=false`), `run-state-record`.

## 2. Gap map (verified)
| Capability | Exists | Gap for #189 |
|---|---|---|
| Root/Child run shape | schemas run-manifest-revision, node-allocation | No executable recursive DAG driver; CLI does 1 assignment/invocation |
| Authority decision receipt | universal_run_authority (C6/C10) | `resolve_authority` not called by native path; no parent→child DERIVED receipt |
| Risk classification | risk_classification R0–R3 + G2 tags | Boundary routes all mutating actions to REQUIRE_APPROVAL; no risk-tier HITL vs HOTL at G2 effect |
| Delegation analogue | materialize_autonomous_preprod_run_authority | pre-prod-only; no general transitive scope/effect closure, risk ceiling, revocation, replay/consumption across parent→child |
| Approval token | approval-token-generation node | single-consumption, all authority flags false; no parent-child delegation semantics |

## 3. Child Run DAG (each its own G0–G6; stop at atomic)
Dependency order: **C1 → C2 → C3 → C4 → C5** (C5 depends on all).

- **C1 — Recursive Run DAG + ChildRun execution/receipt lifecycle.**
  Enhance `universal_run_controller.py` + `universal_run_lifecycle.py`; add `RunDagExecutor`/`ChildRun` runner. Parent/child IDs distinct, immutable lineage, separate gate states, dependency ordering, DAG budget/max-depth/cycle/SINGLE_ACTIVE protections, durable cursor/checkpoint resume, child G6 acceptance + failure propagation. Atomic Run runs full G0–G6 (typed IN_PLACE/NO_TRANSFER_REQUIRED where applicable; no silent skip).
  AC: AC1, AC7(partial), AC8. Owner files: `universal_run_controller.py`, `universal_run_lifecycle.py`, `universal_run_continuation.py`; tests `tests/test_universal_run_dag_v1.py` (new).

- **C2 — Deterministic AUTHORITY DERIVATION evaluator (parent→child).**
  New `universal_run_authority.py::derive_child_authority(parent_grant, child_subject)`: strict subset child scope, repo/branch/head/target, action+transitive-effect closure, risk ceiling, time validity/revocation, ancestor lineage, source-of-approval provenance, actor, replay/consumption. Returns auditable derived-child receipt (NOT a forged Human token). Missing/stale/cross-run/cross-repo/overbroad → fail closed. NO self-grant via file/plan/policy/comment/sibling/registry (C10 extended). Wire `resolve_authority` into the native path.
  AC: AC2(partial), AC4, AC5, AC6. Owner files: `universal_run_authority.py`; tests `tests/test_universal_run_derived_authority_v1.py` (new).

- **C3 — Risk-based EFFECT routing HITL/HOTL (at the G2 effect boundary).**
  Enhance `risk_classification.py` + `universal_run_authority.py::resolve_authority`. R0/R1 + R2 WITHIN valid parent/derived authority → autonomous UR.G2 + HOTL (observable/interruptible, no per-child token). R3 privileged/high-risk or any effect beyond valid authority → hold ONLY that exact effect, request canonical HITL G2 token with precise envelope. Unknown risk / escalation / production/protected → fail closed. Preserve independent sibling progress (EFFECT_HOLD ≠ CONTROL_LOOP_STOP).
  AC: AC2, AC3, AC4. Owner files: `risk_classification.py`, `universal_run_authority.py`, `node-catalog/gate_authority/g2-execution-envelope-render.node.json`; tests `tests/test_universal_run_risk_routing_v1.py` (new).

- **C4 — Runtime continuation / interrupt / lease & audit.**
  Enhance `universal_run_continuation.py` + `universal_run_controller.py` (Controller decision/integration path only, coordinated with continuation ownership). Durable cursor/checkpoint resume, lease contention, idempotent replay, audit ledger for parent/child decisions + HOTL observations + HITL requests.
  AC: AC7, AC8. Owner files: `universal_run_continuation.py`, `universal_run_controller.py`; tests `tests/test_universal_run_continuation_v2.py` (extend).

- **C5 — Independent E2E cross-target validation + SCRUM-781 regression.**
  Wire `agent_runtime_cli.py` to drive the recursive path; integration fixtures exercise SCRUM-781 W1–W6 as CONSUMER in isolated runtime + ≥1 OTHER generic use case (not hardcoded SCRUM-781). Full RED→GREEN AC1–AC12 matrix; same exact source SHA/plan/schema/tests; report historical collection issues separately from regressions; focused + qualification + broader suite.
  AC: AC8, AC9, AC10, AC11, AC12. Owner files: `agent_runtime_cli.py`, new `tests/test_universal_v2_recursive_e2e_v1.py`; regression `tests/test_q0_native_g1_admission.py`, `tests/test_universal_run_*`.

## 4. Acceptance matrix (Controller AC1–AC12) → children
AC1→C1 · AC2→C2/C3 · AC3→C3 · AC4→C2/C3 · AC5→C2 · AC6→C2/C5 · AC7→C1/C4 · AC8→all · AC9→C5 · AC10→C5 · AC11→C2/C4/C5 · AC12→C5.

## 5. Branch / owner / scope decision
- **New governed parent branch** from protected main `f560db71`: `feat/universal-v2-recursive-authority-r1`.
- **New worktree:** `worktrees/gwc/universal-v2-recursive-authority-r1` (isolated, single writer = this executor lane).
- Q0 consumer branch + PR #609 DRAFT untouched. No shared-runtime edits on the Q0 branch.
- Additive commits + fast-forward push to the new branch only; draft PR; independent review of exact HEAD + clean boot.

## 6. Execution policy (per Controller)
Own execution/continuous self-remediation of in-scope atomic child Runs with retries + checkpoint; do NOT request Controller approval after each RED/GREEN; avoid repetitive precheck-only loops; do not stop the whole Parent on one HITL effect (isolate the held effect). Controller validates reports independently against remote code + consumer evidence.

## 7. This-firing deliverable
G1 plan materialized on the new parent branch; C1 implementation is the next child run.
