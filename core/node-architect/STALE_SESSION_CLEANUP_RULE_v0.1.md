# Stale Session Cleanup Rule v0.1

## Status

- Rule ID: `STALE_SESSION_CLEANUP_RULE`
- Version: `0.1`
- Scope: `REVAMP_UPGRADE_GWC`
- Introduced by: `REVAMP-GWC-003`
- Lifecycle: additive node-architect runtime rule

## Purpose

This rule defines how agents identify and clean stale local/session artifacts
without deleting canonical GWC evidence.

It targets temporary runtime folders such as `/mnt/data/...` session folders,
not repository source-of-truth artifacts.

## Cleanup principle

```text
Preserve canonical evidence.
Delete only stale, temporary, non-authoritative artifacts.
Dry-run first.
```

## Preserve by default

Agents MUST preserve:

- repository files;
- `.gwc/tasks/<task-id>/` canonical gate artifacts;
- PR links and head SHAs;
- approval envelopes and commands;
- validation logs;
- failure evidence;
- handoff documents;
- files explicitly marked `preserve: true`;
- any artifact referenced by a current resume token.

## Deletable candidates

Agents MAY mark artifacts as cleanup candidates when all are true:

1. they are outside repository canonical paths;
2. they are temporary runtime/session files;
3. they are older than the configured stale threshold;
4. they are not referenced by an active checkpoint/resume token;
5. they are not evidence for a failed or blocked gate;
6. the cleanup run is dry-run or has explicit cleanup execution approval.

## Default behavior

The cleanup tool MUST run in dry-run mode by default.

A destructive cleanup run MUST require an explicit flag and MUST print what was
removed. It must not remove repository files, hidden `.git` files, or canonical
`.gwc/tasks` evidence.

## Session manifest

A session folder MAY include a manifest file:

```text
.gwc-session.json
```

The manifest can declare:

- `session_id`
- `task_id`
- `created_at_utc`
- `last_used_at_utc`
- `preserve`
- `referenced_by_checkpoint`
- `status`

When the manifest is missing, the tool must classify the folder conservatively.

## Compatibility

This rule is additive and local-agent friendly. It does not introduce automatic
background cleanup, cron jobs, production actions, or repository mutation.
