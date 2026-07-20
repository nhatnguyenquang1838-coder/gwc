# Rental Home Spec-Driven Format Adapter

## Authority and inheritance

This project-local adapter extends [`core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`](../../core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md).

The canonical rule defines the shared `.kiro/specs/<SPEC-ID>/` structure, required `requirements.md`, `design.md`, and `tasks.md` sections, phase discipline, ChatGPT/local-agent task-runtime parity, and GWC authority boundaries.

This file adds only Rental Home-specific triggers, naming, design constraints, and validation requirements. It must not weaken the canonical rule or any protected-base GWC contract.

## Rental Home triggers

Apply spec-driven delivery when a Rental Home request includes or implies:

- create task, tasks, spec, or specs;
- write requirements, design, or implementation tasks;
- implement, add, fix, redesign, or plan a non-trivial Rental Home feature;
- change UI behavior, public interfaces, data flow, RLS, Supabase access, architecture, or migrations.

Read-only analysis and isolated non-behavioral wording fixes may omit a spec when higher-priority instructions permit it.

## Folder and naming

Use exactly:

```text
.kiro/specs/<DOMAIN>-<AREA>-<NN>-<short-kebab-title>/
  requirements.md
  design.md
  tasks.md
```

Examples:

```text
RD-INV-01-debt-report-range-ui
OPS-ALERT-01-notification-read-state
TENANT-DETAIL-01-logic-cleanup
```

Rules:

1. Preserve existing folder casing and project conventions.
2. Split independent workstreams into separate spec folders.
3. Do not use `docs/tasks/<task>/spec.md` for a Kiro feature spec unless the user explicitly requests a non-Kiro archive.
4. Do not relocate historical specs solely to adopt this adapter.

## Requirements additions

In addition to the canonical requirements format:

- use headings exactly as `### Requirement N: <Title>`;
- include numbered, observable EARS-style acceptance criteria;
- state explicit non-goals for schema, RLS, migration, billing, invoice, tenant, and notification behavior when relevant;
- identify affected roles and homes when privacy or authorization is involved.

## Design additions

`design.md` must identify existing mechanisms before proposing new ones and include, where applicable:

- component or module name, suggested path, responsibility, and interface;
- domain types, derived UI models, state models, and mapping rules;
- RLS, role, home, tenant, room, invoice, and service-cycle boundaries;
- correctness and non-regression properties;
- error, empty, loading, and authorization-denied behavior;
- validation commands and migration implications.

### Mandatory implementation constraints

- UI code must not call Supabase directly.
- Use repositories and dependencies exposed through `src/app/dependencies.ts`.
- Reuse existing shared UI components before creating project-local duplicates.
- Do not change database schema, RLS, migrations, production configuration, credentials, or production data unless separately scoped and authorized.
- Do not touch unrelated files or perform opportunistic refactoring.

## Tasks additions

`tasks.md` must:

- include a Mermaid dependency graph;
- use checkbox task states;
- map every implementation and validation task to requirement IDs;
- include inspection, implementation, relevant tests, validation, and final reporting;
- mark blocked, skipped, and optional work explicitly;
- keep database or RLS work in separately visible tasks when applicable.

Allowed task markers:

```text
[ ] not started
[~] in progress
[x] done
[-] blocked or skipped
```

## Validation

Before calling a Rental Home spec Kiro-ready, verify:

```text
requirements.md
- starts with # Requirements Document
- contains Introduction, Glossary, and Requirements
- every requirement has User Story and Acceptance Criteria

design.md
- starts with # Design Document
- contains all canonical design sections
- documents Rental Home architecture and data-access constraints

tasks.md
- starts with # Implementation Plan
- contains Overview, Task Dependency Graph, Tasks, and Notes
- contains Mermaid, checkboxes, and requirement mappings
```

Implementation tasks must include the relevant repository commands, normally:

```bash
npm run typecheck
npm run build
```

Run relevant tests defined by the active repository. Report unavailable checks honestly; do not claim `PASS` without evidence.

## Agent behavior

When implementation is requested:

1. read the canonical rule and this adapter;
2. create or claim the AgentOps/DS Admin task required by the canonical rule;
3. materialize `.gwc/tasks/<task-id>/g0`, `g1`, and `g2` evidence before G2;
4. review the Kiro spec in phase order;
5. execute only the approved task and Files WRITE scope.

Spec approval, DS task state, and `.gwc` artifacts are traceability only. They do not grant repository write, Draft PR, merge, deploy, migration, credential, production configuration, or production-data authority.
