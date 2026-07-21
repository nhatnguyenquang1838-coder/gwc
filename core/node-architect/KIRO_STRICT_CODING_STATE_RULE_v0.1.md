# Kiro Strict Coding State Rule v0.1

## Status

- Rule ID: `KIRO_STRICT_CODING_STATE_RULE`
- Version: `0.1`
- Applies to: `REVAMP_UPGRADE_GWC`
- Scope: Kiro, local coding agents, ChatGPT handoff packs

## Purpose

This rule defines how Kiro or another local coding executor must behave when GWC work is handed off from ChatGPT/FastLane planning into code-producing execution.

## Core rule

```text
Preparation may be lean. Coding must be strict.
```

## Strict coding state

A coding executor may mutate repository files only when all of these are true:

1. task ID is bound;
2. repository and protected base SHA are known;
3. working branch is dedicated to the task;
4. Files READ and Files WRITE are explicit;
5. prohibited actions are listed;
6. G2 approval or equivalent approved envelope is current;
7. changed files remain within Files WRITE;
8. readback diff is performed before PR delivery.

## Kiro state packet

```yaml
schema_version: "0.1"
task_id: REVAMP-GWC-001
state: CODING_READY
repo: nhatnguyenquang1838-coder/gwc
base_sha: <sha>
branch: codex/revamp-upgrade-gwc-20260721
files_read: []
files_write: []
authorized_actions:
  - modify_scoped_files
  - run_validation
  - report_diff
excluded_actions:
  - direct_push_main
  - merge
  - deploy
  - production_data
```

## State values

```text
PREPARED_BY_CHATGPT
CODING_READY
CODING_RUNNING
VALIDATION_RUNNING
DIFF_READBACK_REQUIRED
DRAFT_PR_READY
REPAIR_REQUIRED
BLOCKED_SCOPE_DRIFT
BLOCKED_APPROVAL_EXPIRED
BLOCKED_PROHIBITED_ACTION
```

## Required readback

After coding, the executor must report:

```text
Files READ actual:
Files WRITE actual:
Changed files:
Validation performed:
Validation skipped:
Evidence:
Limitations:
Scope drift: NONE | DETECTED
```

## Forbidden behavior

Kiro/local agents must not:

- widen Files WRITE without stopping for a new approval envelope;
- interpret Jira, TC, DS MCP, or dashboard status as approval;
- merge or enable auto-merge;
- deploy or release;
- touch production data, secrets, credentials, migration, or production config;
- claim validation pass without command output or CI evidence;
- repair outside approved scope.

## Compatibility

This rule is additive. It gives stricter implementation semantics for revamp execution, but it does not replace the existing GWC gate lifecycle.
