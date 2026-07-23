# Runtime Checkpoint Node Family

```text
Task: REVAMP-GWC-019 / SCRUM-74 extension
Batch: batch-04-runtime-checkpoint
Family: runtime_checkpoint
Planned nodes: 14
Authority boundary: G2_EXECUTION
```

## Purpose

This family models the checkpoint/resume layer used by GWC agents during scoped G2 execution.

It keeps checkpoint capture, checkpoint persistence, resume token handling, lease behavior, CAS write guards, state reconciliation, expiry cleanup, and interrupt-flow handling explicit without granting merge, deploy, production, or runtime-engine authority.

## Nodes

| Node | Type | Purpose |
|---|---|---|
| `runtime_checkpoint.checkpoint-capture` | state | Capture a deterministic checkpoint before bounded execution state changes. |
| `runtime_checkpoint.checkpoint-persist` | tool | Persist checkpoint artifacts to the approved workspace without production data access. |
| `runtime_checkpoint.resume-token-generation` | workflow | Generate resume tokens that bind task, gate, base, head, and evidence context. |
| `runtime_checkpoint.resume-token-validation` | gate | Validate resume tokens before continuing interrupted G2 execution. |
| `runtime_checkpoint.lease-acquisition` | connector | Acquire bounded work leases before mutating guarded branch state. |
| `runtime_checkpoint.lease-renewal` | workflow | Renew active leases only when work remains inside the approved scope. |
| `runtime_checkpoint.cas-write-guard` | gate | Guard branch and artifact writes with compare-and-swap expectations. |
| `runtime_checkpoint.state-reconciliation` | workflow | Reconcile local, connector, task, and PR state after interruptions. |
| `runtime_checkpoint.checkpoint-expiry-cleanup` | tool | Clean expired checkpoint hints without deleting governance evidence. |
| `runtime_checkpoint.base-drift-detect` | gate | Detect protected-base drift and create a base-drift interrupt candidate. |
| `runtime_checkpoint.base-drift-assess` | workflow | Classify base drift and determine authority/evidence impact. |
| `runtime_checkpoint.base-drift-revalidate` | workflow | Refresh affected validation and integration evidence before resuming. |
| `runtime_checkpoint.base-drift-reapprove` | gate | Route material drift to a refreshed approval request. |
| `runtime_checkpoint.base-drift-stop` | gate | Fail closed for unsafe, production, secret, history-rewrite, or unassessable drift. |

## Guardrails

```text
✅ exactly 14 nodes
✅ all nodes use authority_boundary=g2_required
✅ all nodes are limited to G2_EXECUTION
✅ checkpoint/resume metadata only
✅ base-drift interrupt flow is metadata/routing only
✅ G4 merge remains separate
✅ no deploy/production authority
✅ no runtime engine implementation
✅ no scheduler/worker implementation
✅ no production data access
✅ no all-81 catalog implementation
```

## Admission criteria

This batch is valid only after:

```text
batch-03-repo-delivery merged to main
exact post-merge CI for batch-03 is available or latest main is verified
runtime node schema validation passes
family validator passes
governance unit tests pass
```

## Explicit exclusions

```text
merge
auto_merge
deploy_release
production_config_data
secrets_credentials
migration
production_data
runtime_engine
scheduler_worker
all_81_node_catalog
```
