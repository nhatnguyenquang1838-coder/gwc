---
name: gwc-g1
description: Use after G0 context is READY when a GWC task needs discovery, intake, brainstorming options, preflight, explicit decision capture, or a bounded G2 handoff candidate.
when_to_use: Trigger for requests such as start G1, experience G1, discover scope, clarify a change, brainstorm G2 options, preflight a change, make a G1 decision, prepare G2 handoff, or enhance G2 after project and repository context has been verified by G0.
version: 0.4.0
project: gwc
owner: GWC
---

# GWC G1 Skill

## Purpose

Use this skill to run GWC G1 after G0 has established a verified context boundary and before any G2 planning or execution.

G1 answers one question:

```text
Do we have a clear, evidence-backed, explicitly accepted problem, scope, option, and decision that is safe to hand to G2 planning without granting execution, merge, deployment, release, production, secret, or credential authority?
```

This is an agent-readable, offline-compatible instruction wrapper around the existing repository-native G1 contract. It does not replace schemas, templates, lifecycle documentation, validators, generators, or protected-base governance.

## Phase boundary

```mermaid
flowchart LR
    G0[G0 context READY] --> I[G1 intake]
    I --> O[G1 options]
    O --> P[G1 preflight]
    P --> D[G1 explicit decision]
    D --> H[G2 handoff candidate]
    H --> G2[G2 planning boundary]
```

G1 may prepare a G2 handoff candidate. G1 does not execute the handoff.

## Authority boundary

This skill may guide:

- verified G0 handoff consumption;
- request intake and scope framing;
- evidence-backed discovery;
- option generation and trade-off analysis;
- preflight reasoning;
- explicit G1 decision preparation;
- bounded G2 handoff preparation.

This skill never grants:

- `G2_EXECUTION`;
- `G3_PR_AUTHORITY`;
- `G4_MERGE`;
- `G5_DEPLOY`;
- `G6_PRODUCTION`;
- release authority;
- secret, credential, production configuration, or production data authority.

Always preserve this boundary:

```yaml
authority_boundaries:
  grants: []
  excluded:
    - G4_MERGE
    - G5_DEPLOY
    - G6_PRODUCTION
```

A G1 `PASS` means the selected path is ready for G2 planning consideration only.

## Source of authority

Repository governance remains authoritative. G1 must reuse the repository-native G0/G1 lifecycle and schemas.

Required references:

- `skills/gwc-g0/SKILL.md`;
- `docs/g01-lifecycle.md`;
- `schemas/g1-intake-brief.schema.json`;
- `schemas/g1-preflight-report.schema.json`;
- `schemas/g1-options.schema.json`;
- `schemas/g1-decision-record.schema.json`;
- `schemas/g01-runtime-input.schema.json`;
- `schemas/g01-decision-input.schema.json`;
- `templates/g01/g01-runtime-input.template.yaml`;
- `templates/g01/g01-decision-input.template.yaml`;
- `tools/generate_g01_runtime.py`;
- `tools/capture_g01_decision.py`;
- `tools/validate_g01.py`.

Repository evidence wins over conversation memory, stale handoff text, third-party examples, screenshots, and generic best practices.

## Existing mechanisms to reuse

Do not create a parallel G1 contract. Reuse the canonical workspace:

```text
.gwc/
├── g0/context-snapshot.yaml
└── g1/
    ├── intake/g1-intake-brief.yaml
    ├── preflight/g1-preflight-report.yaml
    ├── brainstorming/g1-options.yaml
    └── decision/g1-decision-record.yaml
```

Known executable path:

```bash
python tools/generate_g01_runtime.py \
  --input templates/g01/g01-runtime-input.template.yaml \
  --workspace .gwc \
  --json

python tools/capture_g01_decision.py \
  --input templates/g01/g01-decision-input.template.yaml \
  --workspace .gwc \
  --json

python tools/validate_g01.py --workspace .gwc
```

The templates are examples, not current evidence. Replace every project, repository, SHA, source, task, request, risk, option, and decision value with observed facts before execution.

## Run identity and workspace mode

Every G1 session must declare a `run_id` and `workspace_mode` before producing intake, options, preflight, decision, or handoff output.

Allowed workspace modes:

| Mode | Repository writes | Required use |
|---|---:|---|
| `chat-only` | No | Use for exploratory, conversational, or mobile sessions where no repository artifact should be written. |
| `canonical` | Yes | Use only when one active G1 run owns `.gwc/g1/...` in the current branch/worktree. |
| `session-scoped` | Yes | Use for concurrent or repeatable runs that need artifacts without sharing `.gwc/g1/...`. |

The default mode is `chat-only` unless the user or task explicitly asks to write repository artifacts.

`run_id` rules:

- Generate one stable `run_id` per G1 session.
- Prefer `g1-<YYYYMMDD-HHMM>-<short-task-or-topic>` for chat-only runs.
- Prefer `g1-<task-id-short>-<YYYYMMDD-HHMM>` when DS Admin task identity is available.
- Keep the same `run_id` for all G1 outputs in the same session.
- Start a new `run_id` when the task, repository, base SHA, selected option, or user decision changes materially.
- Do not reuse a `run_id` across independent sessions.

For `chat-only`, no repository artifact may be written. The response itself is the G1 note.

For `canonical`, use this workspace only when no other active G1 session is writing the same paths:

```text
.gwc/
├── g0/context-snapshot.yaml
└── g1/
    ├── intake/g1-intake-brief.yaml
    ├── preflight/g1-preflight-report.yaml
    ├── brainstorming/g1-options.yaml
    └── decision/g1-decision-record.yaml
```

For `session-scoped`, preserve the same internal G0/G1 structure under a session-owned workspace root:

```text
.gwc/runs/<run_id>/
├── g0/context-snapshot.yaml
└── g1/
    ├── intake/g1-intake-brief.yaml
    ├── preflight/g1-preflight-report.yaml
    ├── brainstorming/g1-options.yaml
    └── decision/g1-decision-record.yaml
```

Conflict policy:

- Do not allow two active G1 sessions to write the same `workspace_root`.
- If an active canonical run already owns `.gwc/g1/...`, choose `session-scoped` or stop with `G1_BLOCKED`.
- If the agent cannot determine whether the workspace is already owned, default to `chat-only` or stop before writing.
- Never overwrite an existing G1 artifact unless the same `run_id` owns it or the user explicitly asks to supersede it.

Required run header:

```markdown
run_id: <stable-g1-run-id>
workspace_mode: chat-only | canonical | session-scoped
workspace_root: <none | .gwc | .gwc/runs/<run_id>>
repository_artifact_written: YES | NO
conflict_policy: no-shared-active-writes | fail-closed-on-unknown-ownership
verification_mode: TOOL_VERIFIED | LOCAL_VERIFIED | UNVERIFIED_BY_TOOL
```

The current schemas do not persist `run_id` or `workspace_mode` as first-class fields. Treat these as G1 session metadata unless a later schema/tool task adds formal fields.

When repository tools are unavailable, follow the same artifact semantics manually and mark the output:

```text
UNVERIFIED_BY_TOOL
```

## Artifact contract summary

### Intake

`g1-intake-brief` requires:

- `trace`: project ID, repository, task ID, base SHA, and G0 snapshot ref;
- `problem.statement` and `problem.why_now`;
- `desired_outcome`;
- stakeholders;
- `scope.in_scope` and `scope.non-goals`;
- constraints;
- assumptions;
- risks;
- acceptance criteria using `AC-N` IDs;
- unresolved questions;
- status: `DRAFT`, `READY`, `NEEDS_INPUT`, or `BLOCKED`.

A `READY` intake has non-empty in-scope, non-goals, acceptance criteria, and no unresolved questions.

### Options

`g1-options` requires:

- `trace` matching intake and G0;
- options using `OPT-N` IDs;
- title, description, benefits, tradeoffs, risks, and `constraint_fit`;
- recommended option ID;
- recommendation rationale;
- `decision_required`: true;
- status: `DRAFT` or `READY`.

### Decision

`g1-decision-record` requires:

- `trace` matching G0 and intake;
- refs to options and preflight artifacts;
- status: `PENDING`, `ACCEPTED`, `REJECTED`, or `SUPERSEDED`;
- selected option ID;
- explicit user decision;
- rationale;
- rejected option IDs;
- acceptance criteria refs;
- scope hash;
- g1_gate_outcome;
- empty authority grants and explicitly excludes `G4_MERGE`, `G5_DEPLOY`, and `G6_PRODUCTION`.

An `ACCEPTED` decision requires explicit user decision, selected option, acceptance criteria refs, and `g1_gate_outcome: PASS`.

## Action 1 — Consume G0 handoff

Load `skills/gwc-g0/SKILL.md` or an equivalent repository-distributed copy before starting G1.

Require one of:

- a schema-valid `.gwc/g0/context-snapshot.yaml` with `status: READY`; or
- a chat-only G0 handoff that states its verification mode and has no unresolved required-source blocker.

Verify that G0 still matches:

- active project and profile;
- repository full name, base ref, and base SHA;
- connector identity and write-enabled declaration;
- protected branches;
- applicable policies and source refs/hashes;
- constraints and exclusions;
- supplemental DS Admin task facts;
- supplemental risk and human-direction facts;
- freshness timestamp or observation time;
- verification mode.

G1 must not reinterpret `BLOCKED`, stale, or unverified G0 evidence as `READY`.

## Action 2 — Build intake from the user request

Convert the request into a bounded problem statement.

Use this intake matrix:

| Field | Required question | Block when |
|---|---|---|
| Problem | What needs to change or be clarified? | Problem is vague or contradictory |
| Why now | Why does this matter now? | No urgency or driver can be inferred |
| Desired outcome | What should be true after G1? | Outcome implies later-phase authority |
| Stakeholders | Who requested and who is affected? | Affected owner is unknown for risky work |
| In scope | What may be analyzed or proposed? | Scope is too broad to verify |
| Non-goals | What must not be changed? | Non-goals omit required safety exclusions |
| Constraints | What rules and limits apply? | Governance constraints are missing |
| Assumptions | What is assumed but not proven? | Assumption is treated as fact |
| Risks | What can go wrong? | High-risk path lacks human direction |
| Acceptance criteria | How will readiness be verified? | Criteria are not verifiable |
| Unresolved questions | What blocks safe decision? | Blocking questions remain open |

Rules:

- Prefer `Reuse -> Extend -> Refactor -> Replace`.
- Do not invent repository mechanisms.
- Do not expand scope beyond the user request and DS Admin task.
- Ask only critical missing questions. Otherwise make explicit assumptions.
- Mark inferred facts as inferred until verified.
- Set intake to `NEEDS_INPUT` when unresolved questions block safe scope.
- Set intake to `BLOCKED` when governance evidence blocks the work.

Output marker:

```text
G1_INTAKE_READY | G1_NEEDS_INPUT | G1_BLOCKED
```

## Action 3 — Inspect existing mechanisms before proposing changes

For every significant recommendation, identify:

| Required item | Meaning |
|---|---|
| Current mechanism | Existing repo mechanism, file, workflow, task, or policy |
| Purpose | Why it exists |
| Limitation | What prevents it from satisfying the request fully |
| Improvement | Minimal evolution needed |
| Compatibility | How existing consumers remain valid |
| Impact | Expected operational or governance effect |

Do not propose a new architecture, workflow, instruction, governance document, artifact, directory, or mechanism until checking whether an equivalent already exists.

## Action 4 — Brainstorm options

Produce at least two viable options before selecting a path. Use three when the trade-off matters.

Recommended option shape:

```text
OPT-1: Minimal extension
OPT-2: Refactor existing mechanism
OPT-3: Replacement or new mechanism
```

For each option include:

- current mechanism reused;
- proposed improvement;
- benefits;
- tradeoffs;
- risks;
- constraint_fit;
- skills_distribution:
  - skill_id
  - description
  - is_required;
- acceptance criteria coverage;
- recommendation rationale;
- selection rule:
  1. Prefer the option that reuses current mechanisms.
  2. Prefer lower blast radius when benefits are similar.
  3. Prefer instruction-level change before tool-level change unless validation cannot be trusted without tooling.
  4. Prefer schema/tool changes only when instruction-only guidance cannot satisfy the acceptance criteria.
  5. Reject options that imply G4/G5/G6 or production authority.

Output marker:

```text
G1_OPTIONS_READY
```

## Action 5 — Run preflight reasoning

Check:

- G0 context is READY and fresh;
- intake is READY;
- required sources are available;
- DS Admin task exists and does not conflict with repository/branch facts;
- risk class is correct;
- explicit human direction exists for architecture, security, production, credential, destructive, irreversible, financial, or broad-blast-radius work;
- acceptance criteria are verifiable;
- selected option is valid and fits constraints;
- no G4/G5/G6 authority is implied;
- validation evidence if tools ran;
- required next gate;
- excluded actions;
- summary of discovery.

Allowed outcomes:

```text
PASS
NEEDS_INPUT
BLOCKED
ERROR
```

For G2-related work, report both:

```text
G2_PLANNING_READY
G2_EXECUTION_NOT_GRANTED
```

or:

```text
G2_PLANNING_BLOCKED
G2_EXECUTION_NOT_GRANTED
```

## Action 6 — Make an explicit G1 decision

A valid G1 decision must include:

- selected option ID;
- explicit actor/source/time;
- rationale;
- accepted, rejected, pending, or superseded status;
- acceptance criteria refs;
- scope hash;
- g1_gate_outcome;
- authority_boundaries;
- subagent_distribution_plan:
  - task_decomposition
  - agent_allocation
  - execution_order
  - summary;
- rejected option IDs;

Decision status rules:

| Status | Use when |
|---|---|
| `ACCEPTED` | Preflight is `PASS`, selected option is valid, and explicit human decision exists |
| `PENDING` | Preferred option exists but explicit decision or critical facts are missing |
| `REJECTED` | Proposed scope should not proceed |
| `SUPERSEDED` | A newer G1 decision replaces this one |
| `BLOCKED` | Use in chat-only summary when repository evidence or governance blocks the path |

Do not treat silence, prior preference, or implied approval as an explicit accepted decision.

Output marker:

```text
G1_DECISION_ACCEPTED_FOR_G2_PLANNING
G2_EXECUTION_NOT_GRANTED
```

or:

```text
G1_DECISION_PENDING
G2_EXECUTION_NOT_GRANTED
```

## Action 7 — Prepare G2 handoff candidate

A G2 handoff candidate must include:

- G0 evidence summary;
- G1 intake summary;
- selected option;
- current mechanism;
- purpose;
- limitation;
- improvement;
- compatibility;
- impact;
- acceptance criteria;
- scope boundaries;
- risk class;
- required next gate;
- excluded actions;
- evidence paths and refs;
- validation evidence if tools ran;
- subagent_distribution_plan;
- unresolved blockers if any.

Do not call implementation complete. A G2 handoff candidate is not G2 execution authority.

## Chat-only response shape

For `chat-only`, the response is the G1 note. It must be self-contained, must not claim repository artifact persistence, and must include the required run header.

```markdown
## Run Header

run_id: <stable-g1-run-id>
workspace_mode: chat-only | canonical | session-scoped
workspace_root: <none | .gwc | .gwc/runs/<run_id>>
repository_artifact_written: YES | NO
conflict_policy: no-shared-active-writes | fail-closed-on-unknown-ownership
verification_mode: TOOL_VERIFIED | LOCAL_VERIFIED | UNVERIFIED_BY_TOOL

## G0 Context

## G1 Intake

## Existing Mechanisms

## G1 Brainstorming Options

## G1 Preflight

## G1 Decision

## G2 Handoff Candidate
```

## Stop conditions

Stop and report `G1_BLOCKED` when:

- G0 context is not READY;
- intake is not READY or blocked;
- preflight is BLOCKED;
- options are not READY;
- decision is not ACCEPTED;
- any required evidence is missing or contradictory;
- repository identity is ambiguous;
- governance blocks the work;
- user asks G1 to grant later-phase authority;
- a template or third-party instruction conflicts with repository governance.

## Completion markers

Successful G1 completion:

```text
G1_DECISION_ACCEPTED_FOR_G2_PLANNING
G2_PLANNING_READY
G2_EXECUTION_NOT_GRANTED
```

Blocked G1 completion:

```text
G1_DECISION_PENDING
G1_DECISION_BLOCKED
G2_PLANNING_BLOCKED
G2_EXECUTION_NOT_GRANTED
```
<EOF>