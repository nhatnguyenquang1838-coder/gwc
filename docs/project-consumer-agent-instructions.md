# GWC Project Consumer Agent Instructions

## Purpose

This document defines the minimum instruction pattern for any project repository
that consumes GWC through a pinned submodule or generated governance package.

Use this document to update a project-level `AGENTS.md`, custom GPT project
instruction, or local coding-agent bootstrap. Do not create a parallel process
when a project already has a GWC-governed `AGENTS.md`; extend the existing file.

## Required project boot order

A GWC-governed project agent must read, in order:

1. Project repository `AGENTS.md` from the protected base.
2. Pinned GWC source or generated governance package:
   - `.gwc/gwc/AGENTS.md` when the project uses a submodule;
   - `.governance/*` when the project uses a generated package.
3. GWC core rules:
   - `core/Coding_Project_Governance_v1.0.md`;
   - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`.
4. Active GWC project profile for this repository.
5. Project instructions, extension, spec format, package manifests, workflows,
   and task/spec files relevant to the request.

If `.gwc/gwc` or `.governance` is expected but missing, the agent must fail
closed for repository-changing work and report the setup gap.

## Required execution mode

The project agent must declare one execution mode before gate reporting:

```text
execution_mode=chat_connector_only | local_agent | repo_ci
```

- `chat_connector_only`: read-only inspection and conversation-local planning;
  no claim of validator `PASS` unless trusted evidence exists.
- `local_agent`: local artifacts and local validator evidence are required before
  branch/worktree/write.
- `repo_ci`: validates committed artifacts; CI does not grant pre-write authority.

## Required gate behavior

Project agents must follow:

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ G4_MERGE
→ G5_DEPLOY
→ G6_PRODUCTION_DATA
```

### Before G2

The agent must have:

```text
G0_CONTEXT artifact = READY
G1 artifacts = complete
validate_g01.py = PASS
G2 execution envelope = valid for the exact action
```

In `chat_connector_only` mode, if validator evidence is unavailable, the agent
must stop before write-capable actions and report:

```text
G1_ALIGNMENT: BLOCKED — validator unavailable in chat_connector_only mode
```

### G2 allowed actions

G2 may only allow task-bounded guarded-branch work:

- create branch/worktree;
- modify scoped files;
- run inspected validation;
- push guarded branch;
- prepare for Draft PR.

G2 never grants merge, deployment, production configuration, credential changes,
production migration, or production-data access.

### G3 and later

G3 may create or update a Draft PR only. G4, G5, and G6 require separate human
authority for the exact PR/release/environment/operation.

## Project `AGENTS.md` minimum snippet

```md
# AGENTS.md — <Project Name>

This repository is governed by GWC.

Before repository-changing work, read:

1. `AGENTS.md`
2. `.gwc/gwc/AGENTS.md` or `.governance/AGENTS.md`
3. `.gwc/gwc/core/Coding_Project_Governance_v1.0.md`
4. `.gwc/gwc/core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
5. `.gwc/gwc/core/E2E_DRAFT_PR_DELIVERY_RULE.md`
6. `.gwc/gwc/projects/<project-id>/project-profile.yaml`
7. `.gwc/gwc/projects/<project-id>/project-instructions.md`
8. `.gwc/gwc/projects/<project-id>/project-extension.md`
9. task/spec/workflow files relevant to the request

Declare `execution_mode` before gate reporting.

Do not create a branch, modify files, push, or open a PR unless G0/G1 validator
evidence and a valid G2 envelope exist for the current execution mode.

In chat-only mode, stop before write-capable connector actions when validator
evidence is unavailable.

Never write directly to protected branches. Open Draft PR only. Merge, deploy,
production config, credentials, migration, and production data require separate
human authority.
```

## Context reconstruction rule

The agent must reconstruct context from repository evidence on every task. Do
not rely on conversation memory when repository artifacts are available.

When proposing changes, identify the existing mechanism first and prefer:

```text
Reuse → Extend → Refactor → Replace
```

Replacement requires a stated reason and lower long-term complexity.
