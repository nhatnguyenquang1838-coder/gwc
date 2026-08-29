# GWC Project Instructions

## Identity

- Project ID: `gwc`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Runtime agent: `DWC`
- Work-tracking source of truth for new tasks: Jira via Atlassian MCP
- Existing DS Admin and Rental Home tasks are not migrated
- GWC gate artifacts remain authoritative for G0-G6 evidence and approvals

## Default workflow

```text
G0 intake
→ automatic G1 inspection
→ bounded plan
→ automatic G2 execution for non-risk work
→ validation and full diff review
→ automatic G3 Draft PR assembly
→ independent read-only review of the implementation subject
→ exact-current-tip ancestry / evidence-delta / CI verification
→ G3 review closure
→ user review
→ separate G4 merge decision
→ separate G5 deploy decision
→ separate G6 production decision
```

## Global agent behavior

Load and apply the protected-base contracts:

- `core/Agent_Behavior_Semantic_Contract_v1.0.md`;
- `core/Agent_Response_Presentation_Contract_v1.0.md`.

They are additive operational contracts and do not replace the canonical core,
project profile, G0/G1 lifecycle, runtime-specific instructions, or authority
gates.

For non-trivial work, agents must understand and inspect the project before
recommending a change. Existing mechanisms must be evaluated before new ones,
using:

```text
Reuse → Extend → Refactor → Replace
```

A significant recommendation identifies the current mechanism, purpose,
limitation, smallest compatible improvement, compatibility, and impact.

## GWC boot default

GWC boot is on by default for GWC-governed work. A request involving repository,
PR, coding, governance, delivery, validation, Jira projection, Slack projection,
CI, branch, worktree, package, release, deployment, migration, credential,
production configuration, production data, or explicit GWC workflow must run the
protected-base GWC boot unless the user explicitly opts out.

Valid opt-out phrases are explicit and narrow:

```text
NO GWC
Không GWC
loại bỏ GWC
ignored GWC
```

Speed or scope language such as `quick`, `simple`, `just do`, `skip ceremony`,
`minor fix`, `hotfix`, or `rescue` does not disable GWC. It only selects a
bounded workflow inside GWC.

## Agent-only task claim intake

For agent-executed modifying work, task claim intake is mandatory before any
write-capable action.

When the executor is an AI or automated agent, the agent must:

1. create or resolve exactly one Jira issue in project `SCRUM`;
2. read current issue state;
3. claim the task by filling the existing Jira fields `AI Agent` and `Claimed At`;
4. add an intake/claim trace comment when supported;
5. transition or verify the task in the appropriate active state;
6. read back `AI Agent`, `Claimed At`, and status before branch creation or repository mutation.

This requirement applies to agents only. Human-executed work is not blocked by
empty `AI Agent` or `Claimed At` fields. Do not change Jira field definitions for
this rule.

Jira is planning, coordination, and projection. Jira field values or Jira status
never grant G0-G6 authority by themselves.

If the claim is absent, stale, unreadable, or conflicting, the agent must stop
before repository mutation with `AGENT_TASK_CLAIM_BLOCKED` or
`AI_AGENT_CLAIM_CONFLICT`.

## Connector precedence

When repository connector access is available, agents must resolve the
repository connector in this order:

1. GitHub connector.
2. DWC connector.
3. DW1 connector.

Do not silently skip a higher-priority connector that is available and
authorized. If the preferred connector is unavailable, fall back to the next
declared connector in the sequence.

## Graceful fallback

Fail closed before repository mutation or authority escalation, not before all
useful analysis.

- If the active Jira task is unavailable, continue in read-only or
  planning-only mode but do not create a branch, commit, push, or PR.
- If the repository or connector cannot be verified, provide qualified planning
  only and do not claim repository inspection.
- If local validation is unavailable, use existing CI evidence only when the
  change is bounded, non-risk, and the active workflow permits it; record the
  limitation honestly.
- If a preferred diagram or renderer is unavailable, use a text or Mermaid
  fallback unless the missing artifact is required by a higher-priority
  approval contract.

## Response presentation

Use the simplest format that preserves clarity and traceability:

- direct Markdown for simple answers;
- compact tables for status, comparison, and decisions;
- flow-based sections for multi-step work;
- Mermaid for workflow, state, dependency, or architecture relationships;
- SVG/PNG only when requested, required, or materially useful;
- schema-valid YAML/JSON for machine-consumed output;
- standalone fenced blocks for exact user commands.

Do not force visual artifacts onto simple responses and do not claim an artifact
was generated or persisted when it was not.

## DWC repository access

DWC may read the complete verified repository and may create or update any file
required by the active Jira task on a dedicated guarded branch.

Repository access is task-bounded rather than path-bounded. DWC must not use
this permission for unrelated cleanup, broad refactoring, dependency changes,
formatting sweeps, or opportunistic edits.
If the current `main` checkout is dirty, DWC must stop using it and switch to
a fresh isolated worktree before any repository mutation.

## Human direction boundary

Explicit user direction is required before DWC executes a change involving:

- financial impact;
- architecture change;
- security boundary change;
- production configuration;
- credentials or secrets;
- production data;
- destructive or irreversible behavior;
- broad blast radius.

An explicit user request to create the PR grants branch, implementation,
validation, push, and Draft PR authority for the stated scope only.

## G3 independent review and evidence binding

G3 extends the existing Draft PR delivery record; it does not create another
gate. One read-only reviewer evaluates the applicable requirement, design, code,
test, governance, delivery, and CI lanes. For the canonical v1.1 record, review
and implementation validation bind the immutable `implementation_head_sha` and
scope hash, not the SHA of the later commit that contains the evidence record.

The exact current PR head remains mandatory external runtime evidence. Before G3
closure, trusted repository/runtime evidence must prove that the implementation
subject is equal to or an ancestor of the current PR head, that the aggregate
post-implementation delta contains only `.gwc/tasks/<task-id>/g3/**` evidence,
and that every required CI check passes at the exact current PR head.

An evidence-only new PR head recomputes current-tip ancestry, delta, and CI
evidence but does not stale unchanged implementation validation/review. A
non-evidence change after the implementation subject invalidates the binding and
returns to G2. `BLOCKER` findings also return to G2. `MAJOR` findings require
resolution or explicit human risk acceptance bound to the implementation subject
SHA. A `fresh-context` fallback must be labelled as such and must not be
represented as fully independent.

Historical v1.0 delivery records remain immutable provenance. They are not
silently reinterpreted; a new active G3 closure under the repaired contract must
materialize/migrate a v1.1 record.

Reviewer PASS is evidence only. It does not grant G4 merge authority.

## Validation

Before Draft PR creation DWC must:

- parse and validate changed YAML and JSON;
- run applicable repository validation;
- review the full diff against the protected base;
- check for secrets, accidental deletion, generated noise, weakened tests, and
  scope drift;
- record limitations honestly when a validation cannot be executed locally.

Before G3 closure DWC must validate the canonical task-scoped
`g3/delivery-record.yaml` with `tools/validate_g3_delivery.py` using the trusted
external current PR head, verified implementation ancestry, post-implementation
changed paths, and exact-current-tip required CI results. The committed v1.1
record itself must not embed a required self-referential current-tip SHA.

## Permanent exclusions

DWC must never automatically push to `main`, merge, auto-merge, deploy, publish
a release, change production configuration, rotate credentials, access
production data, force-push, delete branches, or rewrite shared history.
