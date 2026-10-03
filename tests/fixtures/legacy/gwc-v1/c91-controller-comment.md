<!-- gwc:mailbox controller protocol=dw.taskcontroller.a2a/v1 run=scrum781-q0-20260920T074727Z seq=91 task=SCRUM-781 -->
## CONTROLLER → EXECUTOR — C91: DISPOSITION — NEEDS_EXACT_HITL — NO STAGING E53 AUTHORIZED

**message_id:** `SCRUM-781-MBX-C2E-20261001-19-C91`
**run_id:** `scrum781-q0-20260920T074727Z`
**session_id:** `20260923_175734_bea63d`
**seq:** `91`
**kind:** `Q0_MAINTENANCE_G1_PLAN_PACKAGE_CONTROLLER_DISPOSITION`

### C90 + E52 consumption
C90 (comment `5747944812`, seq=90, raw-body SHA-256 `f3986077c09eaa09ecd7702fa07799fb8fafb99259d90a6bb422ee53e3de6fe1`) consumed. E52 (comment `5748498883`, seq=52, raw-body SHA-256 `4127f039625096819e42f4de21e0f81757afb82b85007ed31a4ce4afe8bdad0b`) consumed. E52 confirmed: exact-base staging archive has no `.gwc/tasks/SCRUM-781` package; G1 plan package absent; plan-read receipt cannot be verified; ACTIVE G2 envelope not rendered.

### Owner reconciliation
C90 named owner "Controller (DWA/@dwa)". Per Nhat's direct instruction for tick358, Analyzer is Controller; DWA/Hermes is Executor. This correction reconciles the owner mismatch. C90's HOLD content remains valid.

### Source analysis
C86 is G2 scope approval only (`HUMAN-NHAT-SCRUM-781-Q0-AUTHMODEL-BOOTSTRAP-C86`, scope hash `sha256:e3203112b816d7fe8b7aac8e10523beb57ed0073cc4931763b7b590862de7d59`, 13 canonical paths, expires `2026-10-02T13:46:54Z`). It does not materialize/validate a G1 package, does not create a G1 decision, and does not grant G2 execution authority. C87 durable Controller decision is referenced by E52 but the comment is absent from the current repo mailbox — the exact durable plan source is missing. C89 authorizes the staging receipt only in fresh isolated Phase-A workspace; it does not authorize G1 materialization or bypass the G1 plan package requirement. TaskMe read-only child `@session:taskme/20261001_214022_de0537` returned plan-only decomposition, step 0 BLOCKED pending fresh G0/G1 + ACTIVE G2; no materialized plan root/requirements/design/tasks package, no plan-validation PASS. `generate_g01_runtime.py` requires explicit runtime input evidence and fails closed on missing/contradictory input. `capture_g01_decision.py` requires explicit decision input + preflight PASS. No accepted plan source exists to materialize from. C87/C86 source is NOT enough for a generated G1 package — the accepted exact-base G1 plan package/decision is entirely missing.

### C91 decision: NEEDS_EXACT_HITL
No precise staging-only E53 is authorized. The missing piece is the entire accepted exact-base G1 plan package/decision, which has no accepted source. This is a human authority decision, not a materialization step.

- `expected_executor_seq: null` — no Executor dispatch until G1 validation and ACTIVE G2 envelope exist.
- Exact HITL route: `STANDALONE_PATTERN_E_ANALYZER` — Analyzer requests the exact durable approved plan package (or approved not-applicable decision) from Nhat with plan-validation PASS evidence, then renders an ACTIVE G2 envelope.

### Required HITL decision
Nhat (human authority) must supply one of:
1. An exact durable approved G1 plan package (intake + preflight + options + decision with implementation_plan_ref, plan root/revision, validation PASS evidence) bound to exact base `414002f92d48083e7133236346b26e3a2a047e33` and C86 scope hash, OR
2. A schema-valid explicitly approved not-applicable decision with reason.

Release trigger: Controller receives the exact approved plan package/decision with real validator PASS; then an ACTIVE G2 envelope can be rendered and checked; then E53 with precise typed NEXT.

### Gate trace (parent Q0)
G0_CONTEXT: NOT_MATERIALIZED
G1_ALIGNMENT: BLOCKED — no complete accepted exact-base G0/G1 plan package or validation evidence
G2_EXECUTION: NOT_REACHED
G3_PR: NOT_REACHED
G4_MERGE: Nhat-only authority
G5_DEPLOY: NOT_APPLICABLE
G6_PRODUCTION_DATA: NOT_APPLICABLE

### No-repo-effect boundary
No repository effect: no branch, worktree, commit, push, PR, merge, deploy, runtime, production, or file write to the canonical repo. This message is a Controller mailbox write only.

### Evidence
- C90 raw-body SHA-256 confirmed: `f3986077c09eaa09ecd7702fa07799fb8fafb99259d90a6bb422ee53e3de6fe1` (4970 bytes, updated `2026-10-01T17:07:42Z`)
- E52 raw-body SHA-256 confirmed: `4127f039625096819e42f4de21e0f81757afb82b85007ed31a4ce4afe8bdad0b` (4923 bytes, updated `2026-10-01T17:01:46Z`)
- C86 scope hash and 13 canonical paths preserved unchanged.
- C87 durable decision source absent from mailbox — exact missing source identified, not fabricated.
- Validator output: exit 1, BLOCKED, valid=false, six missing artifacts.