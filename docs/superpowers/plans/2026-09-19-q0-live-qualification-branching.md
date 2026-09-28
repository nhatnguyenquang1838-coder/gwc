# Q0 Live Qualification Branching Implementation Plan

> **For agentic workers:** implement this plan task-by-task using isolated task scope and GWC gates.

**Goal:** Materialize the approved Q0 branching and live self-fix semantics as canonical, testable repository contracts before rerunning SCRUM-781 Q0.

**Architecture:** Keep protected-main integration separate from live runtime qualification. Encode the engineering model in one branching contract, one operational runbook, one receipt schema, and one focused contract test; route agents to those artifacts from repository/project instructions.

**Tech Stack:** Markdown, JSON Schema 2020-12, Python/pytest/jsonschema.

**Spec:** `docs/superpowers/specs/2026-09-19-q0-live-qualification-branching-design.md`

## Global Constraints

- No runtime engine implementation change.
- No direct `main` mutation.
- One guarded branch for SCRUM-807.
- No merge/deploy/production action.
- A runtime fix is not `RUNTIME_FIXED` without exact loaded identity + original-incident replay + forward progress.
- Never rewrite a SHA after it is referenced by load/replay evidence.

### Task 1: Canonical branching contract
- Create `core/engineering/Q0_LIVE_QUALIFICATION_BRANCHING_STRATEGY_v1.0.md`.
- Encode branch taxonomy, worktree isolation, immutable evidence, baseline promotion, same/new defect rules, drift and integration boundary.

### Task 2: Q0 live qualification runbook
- Create `core/runbooks/Q0_LIVE_QUALIFICATION_RUNBOOK_v1.0.md`.
- Encode boot, probe loop, defect self-fix loop, LOAD_PROOF, stale-state invalidation, replay, final clean certification and minimum matrix.

### Task 3: Machine-readable receipt
- Create `schemas/q0-live-fix-receipt.schema.json`.
- Require exact candidate/base identities, runtime activation identity, loaded surfaces, invalidation/regeneration, incident fixture, replay and status.

### Task 4: Contract tests
- Create `tests/test_q0_live_qualification_contract.py`.
- Test stale loaded SHA rejection, replay forward-progress requirement, failed-replay rejection, branching invariants, runbook stages and clean final activation.

### Task 5: Instruction routing
- Append a compact Q0 live-qualification routing section to `AGENTS.md` and `projects/gwc/project-instructions.md` that points to the canonical branching contract and runbook rather than duplicating them.

### Task 6: Validate
- Parse JSON schema.
- Run the focused contract test.
- Run applicable instruction/schema validation on the guarded branch.
- Review exact diff against protected base and verify no runtime implementation file changed.
