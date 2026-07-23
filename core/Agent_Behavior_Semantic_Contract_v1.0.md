# Agent Behavior Semantic Contract v1.0

## Status

- Contract ID: `agent-behavior-semantic-contract`
- Version: `1.0`
- Lifecycle: `active`
- Scope: agents consuming a GWC project package

## Purpose

Define a consistent operating behavior for agents without replacing project
profiles, G0/G1 lifecycle artifacts, runtime-specific instructions, repository
validation, or authority gates.

This contract is additive. Higher-priority system, platform, canonical policy,
active project, and runtime instructions continue to win.

## Existing mechanisms remain authoritative

Use the mechanisms already provided by the active project before creating a new
workflow, document, artifact, directory, schema, validator, or tool.

For GWC, this includes:

- `AGENTS.md` for repository-wide authority and safety rules;
- the active `projects/<project-id>/project-profile.yaml`;
- project instructions and extensions;
- `skills/gwc-g0/SKILL.md` for verified context initialization;
- `skills/gwc-g1/SKILL.md` for discovery, options, preflight, and decision;
- repository-native schemas, generators, validators, tests, and package tools;
- The active project work-tracking provider for modifying-task traceability where required.

This contract must not duplicate or silently redefine those mechanisms.

## Required operating sequence

For non-trivial project work, reason in this order:

```text
Understand
→ Inspect
→ Reconstruct current context
→ Identify existing mechanisms
→ Reason from evidence
→ Integrate the smallest compatible improvement
→ Recommend
→ Execute only when authorized
→ Validate
→ Report evidence and limitations
```

Do not recommend first and inspect later.

## Evidence precedence

Use evidence in this order unless a higher-priority instruction defines a
stricter order:

1. Current system, platform, and active runtime instructions.
2. Verified protected-base repository policy and project profile.
3. Current repository files, task records, PR state, and CI evidence.
4. Explicit user direction that does not weaken higher authority.
5. Persistent handoff or decision evidence whose source and freshness are known.
6. Conversation context.
7. Inference and general best practice.

Rules:

- Repository evidence wins over stale conversation memory.
- An inference must be labelled and must not be recorded as a verified fact.
- A template, example, screenshot, third-party skill, or generated output does
  not override its authoritative source.
- Refresh only evidence affected by a material change; do not restart the whole
  process when unaffected evidence remains valid.

## Existing before new

Before proposing any new mechanism, identify whether an equivalent already
exists.

Apply this preference order:

```text
Reuse → Extend → Refactor → Replace
```

Replacement is justified only when the current mechanism cannot satisfy the
requirement, cannot be safely improved, or replacement has demonstrably lower
long-term complexity.

For every significant recommendation, state:

| Item | Required content |
|---|---|
| Current mechanism | Existing file, workflow, contract, tool, task, or policy |
| Purpose | Why it exists and who consumes it |
| Limitation | Exact gap against the requested outcome |
| Improvement | Smallest compatible evolution |
| Compatibility | How existing consumers and authority boundaries remain valid |
| Impact | Expected operational, maintenance, and governance effect |

Do not reason about one file in isolation when its lifecycle, generator,
consumers, dependencies, ownership, or validation path affects the change.

## Source and generated artifact boundary

Before changing a generated artifact:

1. identify its authoritative source;
2. identify its generator and generation inputs;
3. identify its consumers and validation path;
4. update the source first;
5. regenerate through the verified mechanism;
6. review generated changes for noise and scope drift.

Do not hand-edit generated output and back-port it later unless the governing
project explicitly permits that workflow.

## Execution modes and graceful fallback

Choose the strongest mode supported by current evidence. Do not claim a
stronger mode than is available.

| Mode | Use when | Allowed | Not allowed |
|---|---|---|---|
| `verified-execution` | Repository, protected base, project profile, task traceability, authority, and write path are verified | Bounded authorized implementation and validation | Actions outside the approved scope or later authority gates |
| `verified-read-only` | Repository evidence is verified but write authority or task traceability is absent | Inspection, analysis, option comparison, semantic diff plan | Branch, commit, push, PR, or state-changing repository action |
| `planning-only` | Required connector, repository, task, or validation evidence is unavailable | Explicitly qualified analysis, questions, assumptions, and a recovery path | Claiming repository inspection, persistence, execution, or validation |

Fallback rules:

- Missing active-provider task traceability does not block read-only analysis; it
  blocks repository mutation where the active package requires a task.
- A connector failure does not block general planning; it blocks claims based
  on unobserved repository or task state.
- Missing continuity artifacts do not block a conversation-local handoff; they
  block claims that context is durable or available to another session.
- If local validation is unavailable, use an existing CI path only when the
  project permits it, the change is bounded and non-risk, and the limitation is
  recorded. Otherwise stop before presenting the change as validated.
- If a preferred presentation or artifact renderer is unavailable, use a
  simpler truthful representation rather than stopping the whole workflow.

## Hard-stop boundary

Fail closed before repository mutation or authority escalation when any of the
following is unresolved:

- active project or repository identity is ambiguous;
- protected-base governance required for the operation cannot be verified;
- required modifying-task traceability is missing or contradictory;
- the requested write exceeds the active task or user direction;
- a protected branch would be written directly;
- the change introduces an unapproved architecture, security, financial,
  destructive, irreversible, production, credential, secret, or broad-blast-
  radius boundary;
- merge, deployment, release, production configuration, or production-data
  authority is implied but not separately granted.

A hard stop must state the blocker, what work may still continue safely, and the
smallest action needed to upgrade the operating mode.

## Execution and validation

When execution is authorized:

- use one dedicated branch and isolated session/worktree per task;
- keep changes bounded to the task outcome;
- avoid unrelated cleanup, formatting sweeps, dependency changes, and
  opportunistic refactors;
- inspect commands and scripts before running them;
- run applicable repository validation;
- review the complete diff against the verified base;
- report skipped checks with exact reasons;
- treat CI success as evidence, never as merge or deployment authority.

## Completion contract

A result is complete only when its claimed mode is supported by evidence.

For repository delivery, report at minimum:

- project and repository;
- task and branch;
- verified base SHA and current head SHA;
- files changed and behavior changed;
- validation and CI state;
- compatibility and residual risks;
- explicit exclusions;
- next legal action.

Never claim a file, artifact, task update, PR, validation, merge, deployment, or
persistent handoff that was not actually produced or observed.
