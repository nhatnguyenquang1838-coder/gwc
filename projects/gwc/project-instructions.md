# GWC Project Instructions

## Identity

- Project ID: `gwc`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Runtime agent: `DWC`
- Work-tracking source of truth: DS Admin

## Default workflow

```text
G0 intake
→ automatic G1 inspection
→ bounded plan
→ automatic G2 execution for non-risk work
→ validation and full diff review
→ automatic G3 Draft PR
→ user review after CI
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

## Graceful fallback

Fail closed before repository mutation or authority escalation, not before all
useful analysis.

- In `chat_connector_only` mode, exact-ref GitHub/Git/DWC content may populate `/mnt/data` validation workspaces and run validators; connectors remain the repository source of truth and local Git operations grant no authority.
- If DS Admin task traceability is unavailable, continue in read-only or
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
required by the active DS Admin task on a dedicated guarded branch.

Repository access is task-bounded rather than path-bounded. DWC must not use
this permission for unrelated cleanup, broad refactoring, dependency changes,
formatting sweeps, or opportunistic edits.

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

## Validation

Before Draft PR creation DWC must:

- parse and validate changed YAML and JSON;
- run applicable repository validation;
- review the full diff against the protected base;
- check for secrets, accidental deletion, generated noise, weakened tests, and
  scope drift;
- record limitations honestly when a validation cannot be executed locally.

## Permanent exclusions

DWC must never automatically push to `main`, merge, auto-merge, deploy, publish
a release, change production configuration, rotate credentials, access
production data, force-push, delete branches, or rewrite shared history.
