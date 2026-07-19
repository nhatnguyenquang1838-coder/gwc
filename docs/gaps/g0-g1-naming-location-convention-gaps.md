# G0/G1 Naming and Location Convention Gaps

## Discovery date
2026-07-19

## Source
Observed during G0/G1 workflow execution for "improve G2 with Context7 skills for React Vite, Supabase, Vercel" using the new Context7-first skill resolution mechanism.

## Gap 1: Run ID naming convention

### Current state
No standardized `run_id` format exists in AGENTS.md, the Gate Runbook, or the G1 skill. The G1 skill mentions a preferred format (`g1-<YYYYMMDD-HHMM>-<short-task-or-topic>`) but this is advisory only and not enforced by any governance document.

### Observed behavior
The executed workflow used `g1-improve-g2-skill-context7-20260719-0513` as the run_id. This format was chosen ad-hoc without a governing rule.

### Impact
- Inconsistent run IDs across agents and sessions
- No way to deterministically derive a run_id from a task_id
- Hard to correlate runs across DS Admin tasks, branches, and PRs
- No conflict detection when two agents generate the same run_id

### Required fix
Define a canonical `run_id` format in AGENTS.md or the Gate Runbook:
- When DS Admin task ID is available: `g1-<task-id-short>-<YYYYMMDD-HHMM>`
- When no task ID: `g1-<YYYYMMDD-HHMM>-<short-kebab-topic>`
- Maximum length constraint
- Character set (alphanumeric, hyphens only)

## Gap 2: Workspace location convention

### Current state
The Gate Runbook specifies `/mnt/<session>/.gwc/tasks/<task-id>/` for connector sessions, but AGENTS.md does not define:
- When to use canonical `.gwc/` vs `.gwc/tasks/<task-id>/` vs `.gwc/runs/<run_id>/`
- Whether `/mnt` is required or optional for `chat_connector_only` mode
- How to handle workspace conflicts between concurrent runs
- Ownership rules for workspace directories

### Observed behavior
The executed workflow used `.gwc/runs/g1-improve-g2-skill-context7-20260719-0513/` as the workspace root. This was chosen because:
- Canonical `.gwc/g0/` was used for G0 (no conflict)
- Session-scoped `.gwc/runs/<run_id>/` was used for G1 to avoid overwriting canonical paths
- No `/mnt` was used because the agent runs in local_agent mode

### Impact
- Inconsistent workspace roots across agents
- Validator cannot find artifacts when workspace path is non-standard
- Concurrent runs may silently overwrite each other's artifacts
- No cleanup policy for stale workspaces

### Required fix
Define a workspace location decision matrix:

| Mode | G0 location | G1 location | Validator command |
|---|---|---|---|
| `chat_connector_only` with `/mnt` | `/mnt/<session>/.gwc/tasks/<task-id>/g0/` | `/mnt/<session>/.gwc/tasks/<task-id>/g1/` | `--workspace /mnt/<session>/.gwc/tasks/<task-id>` |
| `chat_connector_only` without `/mnt` | `.gwc/tasks/<task-id>/g0/` | `.gwc/tasks/<task-id>/g1/` | `--workspace .gwc/tasks/<task-id>` |
| `local_agent` canonical | `.gwc/g0/` | `.gwc/g1/` | `--workspace .gwc` |
| `local_agent` session-scoped | `.gwc/runs/<run_id>/g0/` | `.gwc/runs/<run_id>/g1/` | `--workspace .gwc/runs/<run_id>` |

## Gap 3: Validation execution requirement

### Current state
The Gate Runbook requires `tools/validate_g01.py` to be run against the task workspace, but:
- No explicit requirement that validation must be run before G2 entry
- No evidence preservation requirement (stdout, exit code, workspace path)
- No retry policy for remediable validation failures
- No distinction between schema validation and cross-artifact validation

### Observed behavior
The executed workflow ran unit tests (`python3 -m unittest ...`) but did not run `tools/validate_g01.py` against the session-scoped workspace. The validator would have failed because:
- The workspace path `.gwc/runs/g1-improve-g2-skill-context7-20260719-0513/` is not the default `.gwc`
- The G0 artifact is at `.gwc/g0/` not under the session workspace
- The `--workspace` argument was not used

### Impact
- G1 cannot be reported as `PASS` without validator evidence
- Agents may skip validation and proceed to G2 with invalid artifacts
- Cross-artifact consistency (trace matching, option existence) is not checked
- No evidence trail for audit

### Required fix
Add to AGENTS.md or Gate Runbook:
- "Before G2 entry, the agent must run `tools/validate_g01.py --workspace <workspace>` and preserve stdout, exit code, and workspace path as evidence."
- "A G1 `PASS` without validator evidence is a gate violation."
- "Remediable validation failures must be fixed and re-validated before G2 entry."

## Gap 4: DS Admin task traceability

### Current state
The Gate Runbook requires DS Admin task traceability when the active profile requires it. The GWC profile has `claim_required_for_e2e: true`. However:
- No explicit step in G0/G1 procedure to resolve or create a DS Admin task
- No task_id format or source requirement
- No state transition requirement before G2

### Observed behavior
The executed workflow used `task_improve-g2-skill-context7` as an informal task ID. No DS Admin task was created, claimed, or transitioned.

### Impact
- G2 execution envelope references a non-existent task
- No traceability between the work and the DS Admin system
- Task claim requirement is not satisfied
- Gate transition cannot be recorded

### Required fix
Add to G0 procedure:
- "Resolve or create a DS Admin task before G0 completion."
- "Record the task ID in G0/G1 trace fields."
- "Verify task state allows the intended transition before G2 entry."

## Gap 5: Approval command format

### Current state
AGENTS.md requires the exact command format:
```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

But:
- No stable `approval_id` generation rule
- No `scope_hash` computation method (normalization, serialization, hashing)
- No expiry formatting requirement (ISO 8601 UTC)
- No placement requirement (standalone fenced text block)

### Observed behavior
The executed workflow generated:
```text
APPROVE G2_EXECUTION APPROVE_G2_improve-g2-skill-context7_20260719 <scope_hash_16> 2026-07-20T05:15:00Z
```

The `approval_id` format `APPROVE_G2_<task>_<date>` was chosen ad-hoc. The `scope_hash` was a placeholder.

### Impact
- Approval commands are not reproducible
- Scope hash cannot be verified
- Expiry format may be misinterpreted
- No deterministic approval_id for audit

### Required fix
Define in AGENTS.md or the Gate Runbook:
- `approval_id` format: `APPROVE_<GATE>_<task-id-short>_<YYYYMMDD>`
- `scope_hash` computation: normalize envelope JSON (sorted keys, no whitespace), SHA-256, prefix 16 chars
- Expiry format: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)
- Placement: standalone fenced text block, one command per block

## Gap 6: Gate reporting format

### Current state
AGENTS.md requires visible gate transitions:
```text
GWC BOOT: PASS — execution_mode=<mode>
G0_CONTEXT: READY|BLOCKED — <evidence or blocker>
G1_ALIGNMENT: PASS|BLOCKED — <validator evidence>
```

But:
- No enforcement of when to report (every gate transition)
- No evidence format requirement (concise, no hidden reasoning)
- No failure consequence for missing reports

### Observed behavior
The executed workflow did not produce the required gate transition report format. Instead, a narrative summary was provided.

### Impact
- Gate status is not machine-parseable
- Audit trail is incomplete
- User cannot quickly determine current gate state
- No blocker evidence for downstream consumers

### Required fix
Add to AGENTS.md:
- "The agent must report gate transitions in the exact format specified."
- "Failure to report a gate transition is a gate completion failure."
- "Reports must be concise and contain only gate status, evidence, decisions, and blockers."

## Summary

| # | Gap | Severity | Fix location |
|---|---|---|---|
| 1 | Run ID naming convention | Medium | AGENTS.md or Gate Runbook |
| 2 | Workspace location convention | High | AGENTS.md and Gate Runbook |
| 3 | Validation execution requirement | High | AGENTS.md and Gate Runbook |
| 4 | DS Admin task traceability | High | G0 procedure in Gate Runbook |
| 5 | Approval command format | Medium | AGENTS.md |
| 6 | Gate reporting format | Low | AGENTS.md |

## Recommended next action

1. Patch AGENTS.md to add run_id format, workspace decision matrix, validation requirement, approval command rules, and gate reporting enforcement.
2. Patch `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md` to add workspace location table, DS Admin task resolution step, and validator evidence preservation.
3. Update `skills/gwc-g1/SKILL.md` to reference the canonical run_id format from AGENTS.md rather than defining its own advisory format.