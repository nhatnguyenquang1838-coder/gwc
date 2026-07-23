# failure_recovery node family

Task: `SCRUM-68`  
Batch: `batch-08-failure-recovery`  
Family: `failure_recovery`  
Planned nodes: 9  
Authority boundary: `G2_EXECUTION_G5_DEPLOY`

This family models timeout, crash, stale-session, retry, reconciliation, fencing, and rollback-routing semantics. It reuses the Runtime Kernel, Checkpoint Resume Rule, stale-session cleanup rule, and failure-simulation matrix. It does not implement a scheduler, worker, deployment engine, or production runtime.

## Scope

Allowed:

- add exactly 9 `failure_recovery` node descriptors;
- add one family README, stdlib validator, focused tests, package exports, and changelog fragment;
- describe G5 status/rollback boundaries without performing deploy, release, publish, reload, or production actions.

Forbidden:

- more than nine nodes in this PR;
- implementing Batch 09 `scale_control`;
- blind retry after ambiguous writes;
- advancing without a valid lease or approval;
- changing `package_version`;
- merge, auto-merge, deploy, release, publish, runtime reload, production configuration/data, credentials, secrets, migration, force-push, branch deletion, or PR-base change.

## Nodes

| Node | Gate | Purpose |
|---|---|---|
| `failure_recovery.timeout-recovery` | G2 | Preserve evidence and recover safely from timeouts. |
| `failure_recovery.crash-checkpoint-recovery` | G2 | Resume from the latest canonical checkpoint after a crash. |
| `failure_recovery.stale-session-reconciliation` | G2 | Reconcile stale ownership before continuation. |
| `failure_recovery.unknown-write-reconciliation` | G2 | Read back ambiguous side effects before retry. |
| `failure_recovery.cas-mismatch-recovery` | G2 | Reload newer checkpoint revisions after CAS conflict. |
| `failure_recovery.lease-expiry-recovery` | G2 | Stop or safely reacquire an expired lease. |
| `failure_recovery.approval-expiry-recovery` | G2 | Regenerate stale approval requests without side effects. |
| `failure_recovery.duplicate-agent-fencing` | G2 | Prevent concurrent agents from advancing one run. |
| `failure_recovery.version-drift-rollback-routing` | G5 | Pin/restart drifted nodes and route rollback evidence only. |

## Guardrails

```text
✅ exactly 9 nodes
✅ previous Batch 07 merged and exact post-merge CI verified
✅ ambiguous write -> readback -> retry decision
✅ checkpoint / lease / approval / version drift fail closed
✅ G5 node is descriptive and separately gated
❌ no Stage 09 content
❌ no runtime engine implementation
❌ no deploy/release/production action
```
