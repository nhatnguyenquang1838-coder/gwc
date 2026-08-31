# Node Architect Research S1–S4 Stage Definitions (Canonical)

**Status**: DRAFT (pending @gwc L4 governance verdict + Nhat approval)
**Author**: DWA (DW Apps Agent) via Pattern N fanout (@ua → @bmad → @gwc → @dwa synthesis)
**Source-of-truth**: `nhatnguyenquang1838-coder/gwc` `origin/main` (current SHA `7abe390b34e3455f026515c464e182a6c8532c16`)
**Compliance**: `Coding_Project_Governance §FLOW-01` (stage-map format) + `RESEARCH_IMPLEMENTATION_BRIDGE_CONTRACT_v0.1.md`

> These definitions resolve the `RESEARCH_GOVERNANCE_BLOCKED` state reported by cron job `f298217f65db` (SCRUM-646). They are **research-only** — no code mutation, no G2 authority granted.

---

## Risk Taxonomy

| Class | Meaning |
|-------|---------|
| **R1** | Read / inventory only — no mutation |
| **R2** | Analysis / impact assessment — no mutation |
| **R3** | Emits binding scope/plan that affects downstream G2 — fail-closed, research-only |
| **R4** | Irreversible / trust-breaking (never in research lane) |

---

## S1 — Research Snapshot & Node Catalog Inventory

- **Canonical purpose**: Capture research baseline + enumerate the 9 node-types as the analysis unit for S2/S3.
- **Entry criteria**: Parent research task exists + approved scope; repo checkout clean at `main`.
- **Required evidence**:
  - `git rev-parse origin/main` → exact current-main SHA
  - `core/node-architect/node-instructions/<family>/*.node-instruction.yaml` enumeration
- **Expected artifact/output**: `S1_SNAPSHOT.md` (snapshot SHA + current-main SHA + node-catalog table 9 types × instances + MISSING flags).
- **Exit criteria** (AGENTS.md §2 style): Snapshot SHA recorded correctly; catalog covers all 9 types; ZERO write.
- **Risk class**: R1
- **Acceptance Criteria**:
  - AC1: `S1_SNAPSHOT.md` contains both `s1_snapshot_sha` and `current_main_sha` (== `git rev-parse origin/main` at capture).
  - AC2: Catalog enumerates exactly 9 types — `failure_recovery`, `gate_authority`, `intake_context`, `package_export`, `repo_delivery`, `runtime_checkpoint`, `scale_control`, `sync_projection`, `validation_quality` — with instance count; each instance maps to a path or is flagged `MISSING`.
  - AC3: Reconcile live dirs (currently 6 materialized) vs 9 → the 3 missing (`failure_recovery`, `intake_context`, `sync_projection`) are listed explicitly as research-gap, not assumed present.
  - AC4: No mutation — command syntax matches bridge §validation (read-only).

---

## S2 — Four-Lens Research Review (L1/L2/L3/L4)

- **Canonical purpose**: Analyze 4 lenses (L1 architecture-correctness, L2 security-trust, L3 reliability-operability, L4 implementability) per SCRUM-269/533 review standard.
- **Entry criteria**: `S1_SNAPSHOT.md` valid; node catalog present.
- **Required evidence**: Repo code paths (`file:line`) for each lens claim; bridge state machine.
- **Expected artifact/output**: `S2_FOUR_LENS.md` — each lens verdict `APPROVE` / `NEEDS_CLARIFICATION` + rationale + residual gap; transition → `HUMAN_REVIEW_REQUIRED` stop.
- **Exit criteria**: 4 lenses have verdicts; every `NEEDS_CLARIFICATION` names a concrete residual (not "intent").
- **Risk class**: R2
- **Acceptance Criteria**:
  - AC1: Each lens (L1–L4) emits verdict + 1-paragraph rationale citing repo evidence (`path:line`).
  - AC2: `NEEDS_CLARIFICATION` must name the EXACT residual gap (per-amendment `CLOSED_BY_DRIFT` / `STILL_UNCLOSED` map).
  - AC3: When verdict is `RESEARCH_VALIDATED` / `WITH_AMENDMENTS` → publish `HUMAN_REVIEW_REQUIRED` and STOP before implementation planning (bridge §95).
  - AC4: Lens-chain blocking (e.g. L2 chained to L1) is recorded, not skipped.
- **Lens → bot mapping** (Pattern N): L1/L2/L3 → `@ua` context + `@bmad` analysis; L4 → `@gwc` governance lens. DWA synthesizes.

---

## S3 — Cross-Node Impact Assessment

- **Canonical purpose**: Map S2 results into concrete impact surface (schema files, registry entries, contract docs) for the 9 node-types + dependency graph across stages.
- **Entry criteria**: S2 has verdict (including `NEEDS_CLARIFICATION` with residual).
- **Required evidence**: Node instruction contract fields (`inputs_schema`, `outputs_schema`, `evidence_required[]`, `allowed_actions[]`, `forbidden_actions[]`, `authority_boundary_ref`, `next_route_contract{}`); bridge "concrete deliverables" requirement.
- **Expected artifact/output**: `S3_IMPACT.md` — impact table per node-type: affected paths + registry/contract changes + risk class + blocks-which-G0.
- **Exit criteria**: Every node-type has an impact entry; no "TBD".
- **Risk class**: R2
- **Acceptance Criteria**:
  - AC1: Each impact entry cites concrete artifact path (`schemas/node-architect/*.json`, `core/node-architect/node-registry.json`, `*.node-instruction.yaml`) — no wildcards.
  - AC2: Cross-stage dependency graph generated (node-type X impact → blocks G0 artifact Y).
  - AC3: Each entry has risk class (R1–R4) assigned clearly.
  - AC4: Node-types with unmaterialized dirs (S1.3) are flagged impact = "research-only, no G0 consumer yet".

---

## S4 — Research→Implementation Bridge Handoff

- **Canonical purpose**: Emit `IMPLEMENTATION_PLAN` contract + `HUMAN_REVIEW_SCOPE_HASH` for G0/G1 to consume; **does NOT self-authorize write**.
- **Entry criteria**: S2 = 4/4 `APPROVE` (or `WITH_AMENDMENTS` already closed); S3 impact present.
- **Required evidence**: Bridge contract §IMPLEMENTATION_PLAN; S1/S2/S3 artifacts; current-main SHA.
- **Expected artifact/output**: `S4_IMPLEMENTATION_PLAN.md` (authorized_paths as file-paths, run_id, `HUMAN_REVIEW_SCOPE_HASH`, G0/G1 artifact map under `.gwc/tasks/<task-id>/`).
- **Exit criteria**: Plan emitted + scope hash; explicit "no G2 authority granted".
- **Risk class**: R3 (wrong scope hash → wrong G2 scope; but research-only, fail-closed)
- **Acceptance Criteria**:
  - AC1: `IMPLEMENTATION_PLAN` contains `HUMAN_REVIEW_SCOPE_HASH` + `authorized_paths` as file paths (no `*`, no `**`).
  - AC2: Artifact asserts `authority_granted: False` — bridge does NOT grant G2; must go through G2 approval chain (bridge: "research phase → G2 approval").
  - AC3: Each G0/G1 downstream artifact maps → concrete path `.gwc/tasks/<task-id>/g0|g1/` + validator command.
  - AC4: Plan binds correct `current_main_sha` (not just `s1_snapshot_sha`) per bridge §41.

---

## Stage Flow

```
S1 (R1) → S2 (R2, four-lens) → S3 (R2, impact) → S4 (R3, bridge handoff)
                                                              ↓
                                                    HUMAN_REVIEW_REQUIRED
                                                              ↓
                                                   G0/G1/G2+ (implementation, separate gate)
```

**Note**: S4 is the research stop-point. Bridge eligibility is a SEPARATE gate (`HUMAN_REVIEW_SCOPE_HASH` + `IMPLEMENTATION_PLAN`), not part of the lens verdict. Research phase never grants G2.

---

## Grounding Evidence (from @ua context, real repo)

- **9 node-catalog types** (verified): `failure_recovery`, `gate_authority`, `intake_context`, `package_export`, `repo_delivery`, `runtime_checkpoint`, `scale_control`, `sync_projection`, `validation_quality`
- **Bridge contract** (`RESEARCH_IMPLEMENTATION_BRIDGE_CONTRACT_v0.1.md`): research → G2 approval chain; no auto-write.
- **Instruction contract fields** (`NODE_INSTRUCTION_CONTRACT_v1.0.md`): `node_id`, `node_type`, `gates[]`, `mode_runtime_required`, `inputs_schema`, `outputs_schema`, `evidence_required[]`, `allowed_actions[]`, `forbidden_actions[]`, `authority_boundary_ref`, `next_route_contract{}`
- **Main SHA**: `7abe390b34e3455f026515c464e182a6c8532c16` (verify against AGENTS.md reference `ea3e44ac...` for drift)

---

#### Artifact-Path Conventions (standardized names for repo persistence)
- `S1_SNAPSHOT.md` — S1 snapshot (SHA + catalog + missing flags)
- `S2_FOUR_LENS.md` — S2 four-lens review verdicts
- `S3_IMPACT.md` — S3 cross-node impact table
- `S4_IMPLEMENTATION_PLAN.md` — S4 bridge handoff (authorized_paths + HUMAN_REVIEW_SCOPE_HASH)\n
## Pending

- [ ] @gwc L4 governance verdict (background run `proc_54b55603848c`)
- [ ] Nhat approval to persist as canonical (currently DRAFT)
- [ ] Update SCRUM-646 with final definitions + close governance gap
