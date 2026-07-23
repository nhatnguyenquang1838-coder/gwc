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
   - `core/Agent_Operating_Runtime_Contract_v1.0.md`;
   - `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`;
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`.
4. `governance/instruction-source-registry.yaml` when present.
5. Active GWC project profile for this repository.
6. Project instructions, extension, spec format, package manifests, workflows,
   and task/spec files relevant to the request.

If `.gwc/gwc` or `.governance` is expected but missing, the agent must fail
closed for repository-changing work and report the setup gap.

## Required operating preamble

For non-trivial work, the project agent must print:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

Then produce an Intake Card containing request type, source instruction, execution mode, risk flags, required reads, Files READ, Files WRITE, required gate, and next action.

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

## Files READ / Files WRITE

Project agents must declare file scope before mutation:

```text
Files READ:
- <path>@<ref-or-sha>

Files WRITE:
- <path>
```

Rules:

```text
No Files READ evidence -> no content-dependent recommendation.
No Files WRITE declaration -> no repository mutation.
New write path -> stop, update scope, regenerate approval request.
Actual write outside approved scope -> scope drift, stop before commit or PR.
```

## Kiro specs and task-runtime parity

For significant governed work moving toward implementation, project agents must follow `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`.

Before G2, a ChatGPT-style agent must create or claim exactly one task through the active project work-tracking provider. For `gwc`, this means a Jira issue via Atlassian MCP. The agent must use legal provider transitions, reach or verify the provider's active-work state during G0/G1 preparation, and materialize the canonical `.gwc/tasks/<task-id>/g0`, `g1`, and `g2` workspace used by local agents.

The task ID, repository, protected-base SHA, branch, and scope hash must remain consistent across the active work-tracking provider and gate artifacts. Kiro specs, task state, and `.gwc` artifacts are traceability only and never grant repository write, PR, merge, deploy, or production authority. Existing legacy task records are not migrated by this rule.

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

### Agent-generated approval commands

Humans do not create approval tokens or scope hashes. The agent must generate an approval request from current evidence and show the exact command for the human to copy-paste:

```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Plain phrases such as `ok`, `approve`, `continue`, `go`, or `yes` are acknowledgement-only and never grant gate authority unless they exactly match an active generated approval command.

### G3 and later

G3 may create or update a Draft PR only. G4, G5, and G6 require separate human
authority for the exact PR/release/environment/operation.

After read-only G5 status verification passes, the agent must project the final
state to the active work-tracking provider when the provider is configured. The
projection must add/update an audit comment, apply the legal provider transition,
read back status/comment/update evidence, and record that readback in the final
report. If provider update or readback fails, report `JIRA_UPDATE_BLOCKED` or the
provider-specific blocker code and keep the gate evidence honest. External task
state is traceability only and never grants GWC authority.

## Project `AGENTS.md` minimum snippet

```md
# AGENTS.md — <Project Name>

This repository is governed by GWC.

Before repository-changing work, read:

1. `AGENTS.md`
2. `.gwc/gwc/AGENTS.md` or `.governance/AGENTS.md`
3. `.gwc/gwc/core/Coding_Project_Governance_v1.0.md`
4. `.gwc/gwc/core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
5. `.gwc/gwc/core/Agent_Operating_Runtime_Contract_v1.0.md`
6. `.gwc/gwc/core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`
7. `.gwc/gwc/core/E2E_DRAFT_PR_DELIVERY_RULE.md`
8. `.gwc/gwc/governance/instruction-source-registry.yaml` when present
9. `.gwc/gwc/projects/<project-id>/project-profile.yaml`
10. `.gwc/gwc/projects/<project-id>/project-instructions.md`
11. `.gwc/gwc/projects/<project-id>/project-extension.md`
12. task/spec/workflow files relevant to the request

Print SOURCE INSTRUCTION and declare `execution_mode` before gate reporting.

Produce an Intake Card with Files READ and Files WRITE before mutation.

Do not create a branch, modify files, push, or open a PR unless G0/G1 validator
evidence and a valid G2 envelope exist for the current execution mode.

In chat-only mode, stop before write-capable connector actions when validator
evidence is unavailable.

Never treat plain `ok`, `approve`, or `continue` as gate authority. The agent
must generate the exact approval command and the human must copy-paste it.

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
