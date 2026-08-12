# G5 Post-Pass Runtime Cleanup Rule v0.1

## Status

- Rule ID: `G5_POST_PASS_RUNTIME_CLEANUP_RULE`
- Version: `0.1`
- Lifecycle: `active`
- Scope: G5 verification and Node Architect runtime finalization

## Purpose

A successful exact-SHA G5 verification must not leave a live observer, lease,
checkpoint, resume cursor, or scheduled continuation behind. This rule defines
the mandatory runtime-only cleanup that follows G5 PASS while preserving all
canonical evidence.

This rule extends `core/G5_CI_VERIFICATION_CONTRACT_v1.0.md` and applies to the
Node Architect runtime described by
`core/node-architect/GATE_NODE_RUNTIME_BINDING_CONTRACT_v1.0.md`.

## Trigger

Cleanup runs only after all of the following are true for the same task and
exact merge SHA:

1. G5 classification is terminal `success` / `PASS`.
2. Required exact-SHA workflow/deployment evidence is persisted and readable.
3. The canonical G5 evidence artifact and trace references have been recorded.

Pending, failed, cancelled, timed-out, SHA-mismatched, or observability-
incomplete G5 states must not use the success cleanup path.

## Mandatory cleanup

The runtime must perform these operations idempotently:

1. Mark G5 checkpoints for the completed merge SHA terminal/retired so they can
   no longer resume polling.
2. Stop G5 observer/poll loops and cancel future continuation wakeups owned by
   the completed G5 verification.
3. Stop lease renewal and release any lease or claim held only for G5
   verification.
4. Retire G5-only resume tokens, continuation cursors, and next-check pointers.
5. Clear ephemeral session/cache pointers owned only by the completed G5 run.
6. Append a cleanup summary containing task ID, merge SHA, cleanup timestamp,
   released runtime resources, preserved evidence references, and final result.

## G6 boundary

When G6 is `not_applicable`, the task runtime may become terminal `completed`
only after the G5 cleanup result is `success`.

When G6 is applicable, cleanup is limited to G5-scoped observer/checkpoint/
continuation state. It must not discard task state required to enter G6; G6
continues under its own explicit authority and fresh runtime state.

## Cleanup failure

A cleanup failure does not rewrite or downgrade valid immutable G5 CI evidence.
Instead:

```text
G5 evidence: PASS
runtime finalization: CLEANUP_REQUIRED
```

The runtime must retry only the idempotent cleanup operations. It must not rerun
or fabricate G5 verification merely to clear runtime state.

## Preservation and prohibitions

Cleanup MUST preserve:

- canonical `.gwc/tasks/<task-id>/` evidence;
- GitHub Actions artifacts and workflow evidence;
- PR comments, merge proof, commit SHAs, approval receipts, and audit logs;
- blocker/failure evidence from earlier attempts.

Cleanup MUST NOT:

- delete repository branches, commits, Pull Requests, or source files;
- delete canonical gate/node evidence;
- deploy, redeploy, publish, release, or reload runtime;
- rotate credentials, modify production configuration/data, or run migrations;
- create detached/background automation solely to finish cleanup later.

## Node Architect compatibility

This is a runtime finalization rule, not a new catalog node. It does not change
the historical 81-node baseline or post-81 extension numbering. Node Architect
must invoke the finalization hook after terminal G5 PASS and record the cleanup
summary in the task/run runtime ledger.
