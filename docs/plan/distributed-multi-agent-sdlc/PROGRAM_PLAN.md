# Distributed Multi-Agent SDLC Program Plan

## 1. Decision

Use **DS MCP as the single execution control plane**. Do not introduce a second orchestrator or a new generic file-writing MCP.

Repository specs remain the source of truth for requirements and design. DS Admin/AgentOps becomes the source of truth for runtime execution state, role ownership, leases, PR/head-SHA binding, CI state, QA evidence, and stage transitions.

## 2. Current-to-Target Assessment

### 2.1 Runtime Source of Truth

**Current mechanism:** DS Admin/AgentOps tracks durable workflows, while Rental Home also treats `TASK.md` and Kiro task files as workflow state.

**Purpose:** Coordinate tasks and retain project-local traceability.

**Limitation:** Runtime state can drift between Task Server and repository Markdown.

**Improvement:** Introduce `tracking_mode: ds_admin_runtime` for Pilot v1. DS Admin is canonical for runtime state; repository task files are projections/evidence for Pilot tasks.

**Compatibility:** Existing non-pilot tasks continue their current repository-driven workflow until migrated.

**Impact:** Removes split-brain execution without a big-bang migration.

### 2.2 Workflow Engine

**Current mechanism:** A linear State Engine creates `analyze_repo → plan_changes → modify_code → create_pr → wait_github_ci → final_report`, with CI failure routed through `fix_ci`.

**Purpose:** Durable asynchronous execution.

**Limitation:** No distinct QA stage or role-bound handoff.

**Improvement:** Pilot adds `qa_validate` and role capability enforcement. End-state moves to versioned declarative workflow templates.

**Compatibility:** Preserve current task types and transition semantics; add one bounded stage first.

**Impact:** Enables a real Dev-to-QA handoff without replacing the State Engine.

### 2.3 File and Action Boundaries

**Current mechanism:** Repository allowlist, protected-branch blocks, branch prefix rules, exact task scope, GWC envelopes, and isolated worktrees.

**Purpose:** Prevent unsafe writes.

**Limitation:** Boundaries are not yet tied consistently to agent role and claimed stage.

**Improvement:** Bind role, stage, repository, branch, exact file set, and authorized action set to the task claim and G2 envelope.

**Compatibility:** Reuses existing GitHub gateway and GWC action-to-gate validation.

**Impact:** Stronger than regex-only directory guards.

### 2.4 QA Evidence

**Current mechanism:** Local test commands, CI status, reviewer gate, and free-form task result artifacts.

**Purpose:** Demonstrate correctness.

**Limitation:** No canonical QA evidence schema tied to exact PR head SHA.

**Improvement:** Add `QaEvidence` with exact repo, PR, head SHA, agent, commands, test/coverage results, diff-scope result, findings, and disposition.

**Compatibility:** Store under existing task result artifacts and event log in Pilot v1.

**Impact:** Makes QA auditable and prevents stale-head approval.

### 2.5 Merge and Deployment

**Current mechanism:** GWC separates G4 merge, G5 deployment, and G6 production authority.

**Purpose:** Preserve human authority for high-impact operations.

**Limitation:** The original guide collapses QA pass, Done, and merge.

**Improvement:** End Pilot at `REVIEW_READYd�hor `ACCEPTED_PENDING_G4`. Merge remains a separate exact human decision.

**Compatibility:** Fully aligned with existing GWC.

**Impact:** Prevents CI or QA from implicitly granting merge/deploy authority.

## 3. Pilot v1 Outcome

Pilot v1 is complete only when both runs succeed:

...