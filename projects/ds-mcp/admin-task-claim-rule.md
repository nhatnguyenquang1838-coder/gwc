
---
instruction_id: ds-mcp-admin-task-claim
version: 1.0.0
lifecycle: active
owner: ds-mcp
minimum_gate: G2_EXECUTION
---

# DS MCP Admin Task Claim Rule

## Mandatory checkpoint

When the active DS MCP package declares
`work_tracking.claim_required_for_e2e: true`, repository execution must follow:

```text
Policy boot
-> G1 inspect task and repository
-> bind task to proposal and approval envelope
-> exact G2 approval
-> claim task through State Engine
-> verify owner and lease
-> create dedicated branch/worktree
-> implement
-> validate
-> reverify claim before remote write
-> push
-> open Draft PR
-> update task through legal State Engine transition
-> final evidence
```

## Hard precondition

```text
No valid claim evidence
-> no branch
-> no worktree
-> no repository modification
-> no command execution that changes repository state
-> no commit
-> no push
-> no Pull Request
```

## Approval binding

The approval envelope must include:

```yaml
work_item:
  provider: ds-admin
  id: <task-id>
  claim_required: true
  expected_repository: <owner/repo>
  expected_owner: <agent-id-or-user-id>
  initial_state: <state-from-protected-state-engine>
  review_state: <state-from-protected-state-engine>
```

Authorized actions must include every external mutation that will occur:

```yaml
authorized_actions:
  - claim_work_item
  - renew_work_item_lease
  - update_work_item_status
```

`release_work_item` is excluded unless explicitly required and approved.

## Required checks

- Work item exists.
- Repository binding matches.
- State is claimable according to the protected State Engine.
- Claim succeeds.
- Claim owner matches the executing identity.
- Lease is valid.
- Scope matches the work item.
- Ownership and lease remain valid before push and PR mutation.
- Final PR number and final head SHA are linked to the task.
- Status transitions use State Engine operations only.

## Failure codes

```text
ADMIN_TASK_REQUIRED
ADMIN_TASK_NOT_FOUND
ADMIN_TASK_NOT_CLAIMABLE
ADMIN_TASK_CLAIM_FAILED
ADMIN_TASK_OWNERSHIP_LOST
ADMIN_TASK_LEASE_EXPIRED
ADMIN_TASK_STATE_DRIFT
ADMIN_TASK_REPOSITORY_MISMATCH
ADMIN_TASK_SCOPE_MISMATCH
ADMIN_TASK_FINAL_SHA_MISMATCH
```

The agent must not silently bypass these failures.
