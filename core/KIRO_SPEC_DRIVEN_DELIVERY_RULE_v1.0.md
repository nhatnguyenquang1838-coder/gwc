---
policy_id: KIRO_SPEC_DRIVEN_DELIVERY_RULE
version: "1.0"
status: active
authoritative: false
policy_scope: reusable_spec_planning_and_delivery
applies_to:
  - feature_planning
  - non_trivial_implementation
  - ui_redesign
  - architecture_change
  - migration
---

# Kiro Spec-Driven Delivery Rule v1.0

## 1. Purpose

Standardize reusable Kiro spec-driven planning across GWC-governed projects while preserving GWC gate authority and project-local constraints.

This rule is additive. It does not replace `Coding_Project_Governance_v1.0`, `GATE_LIFECYCLE_CONTRACT_v1.0`, project profiles, project extensions, approval envelopes, or stricter protected-base instructions.

## 2. Trigger

Create or update a Kiro spec for a material feature, non-trivial implementation, UI redesign, public interface or workflow change, architecture change, migration, or other work where requirements/design/task traceability materially reduces delivery risk.

A project may define stricter triggers. A trivial wording correction, isolated non-behavioral fix, or read-only analysis may omit a spec when the active project instructions permit it.

## 3. Canonical folder

```text
.kiro/specs/<SPEC-ID-kebab-case>/
  requirements.md
  design.md
  tasks.md
```

Rules:

1. Use one folder per coherent delivery outcome.
2. Split independent workstreams into separate spec folders.
3. Preserve existing project naming conventions when they are stricter.
4. Do not place canonical Kiro feature specs under an unrelated task/archive folder.

## 4. `requirements.md`

The file MUST start with `# Requirements Document` and contain, in order:

```markdown
# Requirements Document

## Introduction

## Glossary

## Requirements
```

Each requirement SHOULD use:

```markdown
### Requirement N: <Title>

**User Story:** As a <role>, I want <capability>, so that <benefit>.

#### Acceptance Criteria

1. WHEN <condition> THEN the system SHALL <behavior>.
```

Acceptance criteria MUST be observable and verifiable. Use `SHALL` for mandatory behavior, `SHOULD` for preferred behavior, and `SHALL NOT` or `MUST NOT` for prohibitions.

## 5. `design.md`

The file MUST start with `# Design Document` and contain:

```markdown
# Design Document

## Overview

## Architecture

## Components and Interfaces

## Data Models

## Correctness Properties

## Error Handling

## Testing Strategy

## Implementation Constraints
```

The design MUST identify existing mechanisms to reuse before introducing a new mechanism. Components, interfaces, models, correctness properties, and tests SHOULD trace to requirement IDs.

## 6. `tasks.md`

The file MUST start with `# Implementation Plan` and contain:

```markdown
# Implementation Plan

## Overview

## Task Dependency Graph

## Tasks

## Notes
```

Tasks MUST:

- be ordered by dependency;
- use checkboxes or an equivalent trackable status format;
- identify relevant requirement IDs;
- include validation work;
- avoid unrelated cleanup or opportunistic refactoring;
- identify blocked or optional tasks explicitly.

The dependency graph SHOULD use Mermaid when the task relationship is non-linear.

## 7. Phase discipline

Use this planning sequence:

```text
requirements → review → design → review → tasks → review → implementation
```

A later document MUST NOT silently contradict an approved earlier document. Material requirement or design change requires updating affected downstream documents and their traceability.

## 8. ChatGPT and local-agent task-runtime parity

For significant governed work that is moving from planning toward implementation, a ChatGPT-style agent MUST use the same task trace and task-scoped GWC workspace pattern as a local agent.

Before entering G2, the agent MUST:

1. resolve or create exactly one task through the active profile's work-tracking provider (Jira via Atlassian MCP for `gwc`);
2. read the live task state contract and use legal idempotent transitions only;
3. transition or verify the task in `agent_running` while G0/G1 preparation is active;
4. materialize the canonical task workspace under:

```text
.gwc/tasks/<task-id>/
  g0/context-snapshot.yaml
  g1/intake/g1-intake-brief.yaml
  g1/preflight/g1-preflight-report.yaml
  g1/brainstorming/g1-options.yaml
  g1/decision/g1-decision-record.yaml
  g2/execution-envelope.yaml
```

5. bind the task ID, repository, protected-base SHA, scope hash, and branch consistently across the task state and gate artifacts;
6. run or cite the protected-base G0/G1 validator before requesting G2;
7. synchronize the active work-tracking provider state at each later gate boundary.

In `chat_connector_only` mode, the workspace MAY be materialized in a unique isolated `/mnt` session before approval. Repository persistence of `.gwc` artifacts is itself a G2 write and MUST NOT occur before valid G2 authority.

The agent MUST NOT invent a parallel task artifact format when the repository already provides the task-scoped `.gwc/tasks/<task-id>/g0`, `g1`, and `g2` mechanism.

Task creation, `agent_running`, Kiro spec approval, and valid G0/G1 artifacts provide traceability only. They do not grant repository write, Draft PR, merge, deploy, release, production configuration, credential, migration, or production-data authority.

## 9. GWC authority boundary

Kiro specs are planning and traceability artifacts only.

```text
Spec existence or approval DOES NOT authorize repository writes.
Task selection or completion DOES NOT authorize a Draft PR.
Kiro approval DOES NOT authorize merge, deploy, or production operations.
```

- Creating or updating spec files in a repository is a write action and requires the applicable G2 evidence and authority.
- Implementation requires G2 and must remain within Files WRITE and the active execution envelope.
- Draft PR delivery follows G3.
- Merge requires a separate G4 approval. Deploy/release and production configuration, credentials, migrations, and production data remain separately gated under G5/G6 as applicable.

## 10. Project-local adapters

A project-local rule MAY add:

- domain-specific spec IDs and naming;
- architecture and dependency constraints;
- required commands or tests;
- UI, API, data, RLS, security, or migration requirements;
- additional sections or templates.

A project-local adapter MUST:

1. reference this canonical rule;
2. state only additions or stricter constraints;
3. avoid duplicating the complete canonical template;
4. never weaken GWC authority, validation, or evidence requirements.

## 11. Compatibility and migration

Existing project-local spec rules remain valid when they are compatible. Adoption SHOULD be additive:

```text
Find existing → Reuse → Extract shared core → Retain local adapter
```

Do not delete or relocate existing specs solely to adopt this rule. Migrate older formats only when a task explicitly requires it.

## 12. Validation checklist

A Kiro-ready spec passes when:

- the canonical folder contains all three required files;
- required top-level headings exist;
- requirements include user stories and verifiable acceptance criteria;
- design traces important decisions and correctness properties to requirements;
- tasks are dependency-aware and map to requirements;
- project-local constraints are preserved;
- the spec does not claim or imply authority beyond the current GWC gate.

## 13. Task Me / Kiro implementation-plan handoff

For every task moving from G1 planning to implementation, G1 MUST deterministically classify implementation-plan applicability.

### 13.1 Applicability

Use `applicability: required` for material or multi-step implementation, schema/runtime changes, architecture changes, migrations, or work that benefits from codebase or knowledge-graph analysis, impact analysis, complexity analysis, dependency ordering, file/symbol targeting, or test design.

Use `applicability: not_applicable` only for read-only discovery, status checks, approval recording, communication-only or projection-only work, or a clearly trivial bounded edit. The G1 evidence MUST include the reason; `PLAN_NOT_APPLICABLE` is not an implicit default.

### 13.2 Resolution order

When a plan is required, G1 MUST use this order:

1. Search the target repository for a current task-compatible Kiro spec or other project-approved canonical plan.
2. Reuse it only when task identity, repository, protected-base SHA, requirements, design, task decomposition, and current codebase state match.
3. When no valid plan exists, call Task Me when it is applicable and available.
4. When Task Me is unavailable, unsupported, or not applicable, generate the canonical Kiro three-file package directly and record the fallback reason.

Duplicate or conflicting plan candidates MUST block G1 until one canonical plan is selected or the conflict is resolved.

### 13.3 G1 evidence

Plan-aware G1 artifacts MUST carry one structured `implementation_plan` object in preflight and one immutable `implementation_plan_ref` in the accepted decision. They MUST bind:

- applicability and reason;
- selected source: `existing_kiro`, `task_me`, `generated_kiro`, or `plan_not_applicable`;
- Task Me applicability, availability, invocation, and fallback reason;
- canonical task UID, repository, and protected-base SHA;
- plan root plus requirements, design, and tasks paths;
- exact plan revision;
- validation status and durable validation evidence;
- generator identity and UTC timestamp.

Legacy artifacts that contain neither field remain compatible. A partial pair is invalid. When applicability is required, G1 `PASS` is forbidden if a path, revision, validation result, identity binding, or durable evidence is missing, stale, invalid, or inconsistent.

### 13.4 G2 read-before-write

The accepted G1 plan reference MUST be copied unchanged into the G2 execution envelope. Before the first G2 repository mutation, the executor MUST:

1. read all three plan files or the approved equivalent package;
2. verify canonical task UID, repository, protected-base SHA, and plan revision;
3. verify repository state and approved scope remain consistent;
4. record `.gwc/tasks/<task-id>/g2/plan-read-receipt.yaml` with the exact paths read and verification result;
5. run `tools/validate_g01.py --gate G2_EXECUTION`.

A missing plan, missing read receipt, stale revision, base drift, scope mismatch, ownership conflict, or unresolved dependency MUST stop G2 and return the task to G1. G2 MUST NOT silently regenerate, widen, or substitute the plan after approval.

The read receipt and plan reference MUST remain visible in G2/G3 evidence and the Draft PR body. They grant no G4, G5, or G6 authority.
