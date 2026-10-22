# G1 Design / Implementation Plan — COMMAND #189
## GENERIC Universal V2: recursive G0→G6 + inherited/derived authority + risk-based HITL/HOTL

- **Controller command:** #189 (GitHub #595 comment 6344695425), from: GPT, human-authorized DESIGN+IMPLEMENTATION.
- **Run:** scrum781-q0-fresh-20261010-r1 · **Parent gate:** UR.G2 / RUN_NOT_COMPLETE.
- **Protected main base (re-checked):** `f560db71705d89d0ded2a5efbcaeb4c7c4dafab8`.
- **Mode:** GENERIC shared-runtime work. NOT a Q0-consumer change. Separate governed parent branch/worktree required (do NOT edit shared runtime on the Q0-only branch `fix/SCRUM-781-q0-fresh-20261010-r1`).
- **Hard boundaries (unchanged):** A stays closed safe; B (real Q0 active selector/checkpoint/cursor) unapproved; no protected-main merge, deploy, production, secret, migration, destructive, G6-human-acceptance widening. HOTL = observation, not approval.

---

## 1. Canonical source map (ENHANCE, do not replace) — CORRECTED per COMMAND #191 F1/F2
CORRECTION (F1/F2, exact-read against protected main f560db71): the earlier integration
lane's claim of `universal_run_controller.py` / `universal_run_continuation.py` /
`universal_run_execution.py` / `universal_run_executor.py` is FALSE — those paths 404 on
main. The real host path is below. The pure/transport-neutral universal_run_* modules
that DO exist are listed first; the runtime integration seam is the agent host, not a
fictional controller.

**Actual live host seam (verified):**
`tools/node_architect/agent_runtime_cli.py::main` →
`tools/node_architect/agent_runtime_entrypoint.py::run_agent_runtime_event(...)` →
`resolve_gate_node_route` (route_profile, node_registry, graph_registry, context, root)
→ node dispatch; driven by `run_agent_runtime_loop(event_kwargs, max_iterations=32)`.
`run_agent_runtime_event` already accepts `run_id`, `gate`, `requested_action`, `authority`,
`state` (LiveRuntimeState), `capability_handlers`, `readback_handler`, `evidence_root`,
`node_registry`, `graph_registry` — the natural recursive seam: one event = one node hop,
and authority/state flow through the event envelope. C1/C2/C3/C4 must route through THIS
path, not a parallel controller.

**Existing pure/transport-neutral modules to enhance (all committed on main):**
- `universal_run_kernel.py` (UNIVERSAL_PROFILE, kernel errors)
- `universal_run_lifecycle.py`, `universal_run_topology.py`, `universal_run_node.py`,
  `universal_run_state.py`, `universal_run_plan.py`
- `universal_run_authority.py` — `resolve_authority()` (lines 174–198) matches receipt→exact
  task_id+action; C6 orthogonal authority, C10 self-grant/stale fail-closed already enforced.
- `risk_classification.py::render_risk_classification` — R0–R3; R0/R1 `G2_AUTOMATIC_BOUNDED`,
  R2/R3 `G2_HUMAN_DIRECTION` (see F-correction: R2 routing is authority-gated, not blanket).
- `derive_task_authority.py::derive_g2_authority` — manifest-based evaluator (NOT inherited
  ChildRun authority).
- `materialize_autonomous_preprod_run_authority.py` — strongest existing delegation analogue
  (codes: `AUTONOMOUS_CHILD_G2_AUTHORIZED`, `AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED`,
  `AUTONOMOUS_HEAD_DRIFT`, …) but pre-prod-specific, no general recursive parent→child contract.

**Node catalog (CORRECTED path per F2):** `core/node-architect/node-catalog/gate_authority/`
(`approval-token-generation`, `g2-execution-envelope-render`, `authority-boundary-check`,
`blocked-action-escalation`, `scope-hash-calculation`); `intake_context/risk-classification.node.json`.

**Schemas already present (reuse):** `run-manifest-revision` (ROOT vs CHILD; child requires
parent+allocation), `node-allocation` (child instance policy, independent-boundary),
`child-run-materialization-receipt` (DAG budget, SINGLE_ACTIVE, max depth, provenance, content
digest), `context-snapshot` (`authority_effect_boundary.grants_authority=false`), `run-state-record`.

## 2. Gap map (verified)
| Capability | Exists | Gap for #189 |
|---|---|---|
| Root/Child run shape | schemas run-manifest-revision, node-allocation | No executable recursive DAG driver; the host event loop (`run_agent_runtime_event`) does one node hop per event and stops at the gate boundary — recursion + authority evaluators are NOT wired into it. |
| Authority decision receipt | universal_run_authority (C6/C10) | `resolve_authority` not called by the native path; no parent→child DERIVED receipt. |
| Risk classification | risk_classification R0–R3 + G2 tags | Boundary routes all mutating actions to REQUIRE_APPROVAL; no risk-tier HITL vs HOTL at the actual G2 effect. |
| Delegation analogue | materialize_autonomous_preprod_run_authority | pre-prod-only; no general transitive scope/effect closure, risk ceiling, revocation, replay/consumption across parent→child. |
| Approval token | approval-token-generation node | single-consumption, all authority flags false; no parent-child delegation semantics. |

## 3. Child Run DAG (each its own G0–G6; stop at atomic)
CORRECTION (F4): dependencies are TRUE data dependencies, not an artificial serial stop.
- **C1 — Recursive Run DAG + ChildRun execution/receipt lifecycle.**
  Enhance `universal_run_topology.py` + `universal_run_lifecycle.py`; add a recursive
  driver that runs through the REAL host seam (`run_agent_runtime_event` →
  `resolve_gate_node_route` → node dispatch), NOT a parallel controller. Parent/child
  IDs distinct, immutable lineage, separate gate states, dependency ordering, DAG
  typed IN_PLACE/NO_TRANSFER_REQUIRED where applicable; no silent skip. The current
  checkpoint mapping is an in-memory replay prototype only; disk/process-crash durability,
  sealed receipts, CAS and persistent leases belong to C4 and are not claimed by C1.
  AC: AC1, AC7(partial), AC8. Owner files: `universal_run_topology.py`,
  `universal_run_lifecycle.py`, `universal_run_node.py`; tests `tests/test_universal_run_dag_v1.py` (new).
  DEPENDS ON: nothing (foundational topology/kernel/lifecycle/state/plan are pure and already
  committed; C2/C4 consume C1's topology).

- **C2 — Deterministic AUTHORITY DERIVATION evaluator (parent→child).**
  New `universal_run_authority.py::derive_child_authority(parent_grant, child_subject)`:
  strict subset child scope, repo/branch/head/target, action+transitive-effect closure,
  risk ceiling, time validity/revocation, ancestor lineage, source-of-approval provenance,
  actor, replay/consumption. Returns auditable derived-child receipt (NOT a forged Human
  token). Missing/stale/cross-run/cross-repo/overbroad → fail closed. NO self-grant via
  file/plan/policy/comment/sibling/registry (C10 extended). Wire `resolve_authority` into
  the native path.
  AC: AC2(partial), AC4, AC5, AC6. Owner files: `universal_run_authority.py`;
  tests `tests/test_universal_run_derived_authority_v1.py` (new).
  DEPENDS ON: C1 (consumes the recursive run lineage/child identity it produces).

- **C3 — Risk-based EFFECT routing HITL/HOTL (at the G2 effect boundary).**
  Enhance `risk_classification.py` + `universal_run_authority.py::resolve_authority`.
  CORRECTION (F-correction): R2 is NOT blanket `G2_HUMAN_DIRECTION`. Routing is
  authority-gated: R0/R1 + R2 WITHIN valid parent/derived authority → autonomous UR.G2 +
  HOTL (observable/interruptible, no per-child token). R3 privileged/high-risk or any effect
  beyond valid authority → hold ONLY that exact effect, request canonical HITL G2 token with
  precise envelope. Unknown risk / escalation / production/protected → fail closed. Preserve
  independent sibling progress (EFFECT_HOLD ≠ CONTROL_LOOP_STOP).
  AC: AC2, AC3, AC4. Owner files: `risk_classification.py`, `universal_run_authority.py`,
  `node-catalog/gate_authority/g2-execution-envelope-render.node.json`;
  tests `tests/test_universal_run_risk_routing_v1.py` (new).
  DEPENDS ON: C2 (needs the derived authority to decide HOTL vs HITL).

- **C4 — Runtime continuation / interrupt / lease & audit.**
  Enhance `universal_run_continuation.py` + `universal_run_lifecycle.py` (Controller
  decision/integration path only, coordinated with lifecycle ownership). Durable
  cursor/checkpoint resume, lease contention, idempotent replay, audit ledger for
  parent/child decisions + HOTL observations + HITL requests. Wire to the REAL CLI path
  (`agent_runtime_cli.main` → `run_agent_runtime_event`), not a nonexistent
  `universal_run_continuation.py`.
  AC: AC7, AC8. Owner files: `universal_run_continuation.py`,
  `universal_run_lifecycle.py`; tests `tests/test_universal_run_continuation_v2.py` (extend).
  DEPENDS ON: C1 (topology/child identity) AND C3 (the effects it must hold/continue).

- **C5 — Independent E2E cross-target validation + SCRUM-781 regression.**
  Wire `agent_runtime_cli.py` + `agent_runtime_entrypoint.py` to drive the recursive path;
  integration fixtures exercise SCRUM-781 W1–W6 as CONSUMER in isolated runtime + ≥1 OTHER
  generic domain fixture (not hardcoded SCRUM-781). Full RED→GREEN AC1–AC12 matrix; same
  exact source SHA/plan/schema/tests; report historical collection issues separately from
  regressions; focused + qualification + broader suite.
  AC: AC8, AC9, AC10, AC11, AC12. Owner files: `agent_runtime_cli.py`,
  `agent_runtime_entrypoint.py`, new `tests/test_universal_v2_recursive_e2e_v1.py`;
  regression `tests/test_q0_native_g1_admission.py`, `tests/test_universal_run_*`.
  DEPENDS ON: C1, C2, C3, C4 (all).

## 3b. Generic Root Run identity (CORRECTION per F3)
The parent Root Run is a DISTINCT immutable shared-runtime identity, NOT the Q0 consumer
run `scrum781-q0-fresh-20261010-r1`. Per `run-manifest-revision.schema.json`: Root has null
parent/allocation refs; every Child requires parent + allocation. Consumer edge to
SCRUM-781/Q0 is recorded explicitly on the Root manifest, and `child_run_id == parent_run_id`
or a self-parent loop is rejected by the validator. This GitHub #595 issue remains
communication transport/mailbox, NOT identity-proof that every generic child is an
SCRUM-781 ChildRun.

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
