# Repo Delivery Node Family

```text
Task: REVAMP-GWC-018
Batch: batch-03-repo-delivery
Family: repo_delivery
Planned nodes: 9
Authority boundary: G2_EXECUTION_G3_PR
```

## Purpose

This family models the repository delivery layer used by GWC agents after a scoped G2 approval has been granted.

It keeps branch creation, bounded writes, diff readback, Draft PR creation, CI capture, G3 readiness, and PR blocker checks explicit without granting merge, deploy, production, or all-catalog authority.

## Nodes

| Node | Type | Purpose |
|---|---|---|
| `repo_delivery.branch-creation` | connector | Create guarded branches from exact approved base SHA. |
| `repo_delivery.base-drift-check` | gate | Detect base drift before branch creation, PR updates, and merge-bound checks. |
| `repo_delivery.scoped-file-write` | tool | Write only files allowed by the active G2 execution envelope. |
| `repo_delivery.diff-readback` | workflow | Read back compare metadata and changed-file scope after writes. |
| `repo_delivery.draft-pr-creation` | connector | Open Draft PRs with approved scope, base, head, and exclusions. |
| `repo_delivery.ci-run-capture` | tool | Capture exact-head CI workflow status for G3 evidence. |
| `repo_delivery.ci-failure-repair` | workflow | Repair CI failures within the same bounded PR scope. |
| `repo_delivery.ready-for-review-promotion` | connector | Promote Draft PR to Ready for Review only after G3 criteria pass. |
| `repo_delivery.pr-blocker-check` | gate | Check mergeability, review threads, review submissions, and unresolved blockers. |

## Guardrails

```text
✅ exactly 9 nodes
✅ all nodes use authority_boundary=g2_required
✅ nodes are limited to G2_EXECUTION and/or G3_PR
✅ Draft PR only under G2
✅ G4 merge remains separate
✅ no deploy/production authority
✅ no runtime engine implementation
✅ no all-81 catalog implementation
```

## Admission criteria

This batch is valid only after:

```text
batch-02-gate-authority merged to main
exact post-merge CI for batch-02 is available or latest main is verified
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
runtime_engine
scheduler_worker
all_81_node_catalog
```
