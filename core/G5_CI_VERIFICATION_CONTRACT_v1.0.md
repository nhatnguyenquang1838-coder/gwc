# G5 CI Verification Contract v1.0

## Purpose

This contract defines the read-only G5 status-verification runtime for GitHub Actions after a G4 merge. It turns the existing exact-SHA rule into an executable resolver, evidence bundle, and checkpoint protocol.

G5 CI verification is not a deployment authority. It never permits merge, deploy, release, publish, runtime reload, production configuration, credentials, secrets, migrations, or production-data operations.

## Scope

```text
Gate: G5_DEPLOY
Default action: G5_STATUS_VERIFY
Authority: automatic read-only after G4 merge
Manual G5 approval: required only for manual deploy/redeploy/release/publish/runtime reload
```

## Required input

A G5 CI verification run must be bound to:

```yaml
task_id: <task-id>
repository: owner/repo
base_ref: main
merge_commit_sha: <40-char sha>
g4_approval_id: <id>
g4_scope_hash: sha256:<hash>
required_workflows:
  - <workflow name or file>
known_run_ids: []        # optional fallback evidence from G4/G3/CI notes
connector_capabilities:
  - fetch_commit_workflow_runs
  - get_commit_combined_status
  - fetch_workflow_run_jobs
  - fetch_workflow_run_artifacts
  - fetch_workflow_job_steps
```

## Runtime family mapping

G5 verification reuses the existing runtime catalog instead of creating a new top-level gate or catalog family.

| Capability | Existing family | Runtime node role |
|---|---|---|
| protected base / merge SHA binding | `repo_delivery` | resolve commit and workflow identity |
| pending state persistence | `runtime_checkpoint` | persist and resume same SHA |
| failure classification | `failure_recovery` | route failed/cancelled/timeout states |
| evidence quality | `validation_quality` | reject stale, neutral, skipped, or unrelated checks |
| audit projection | `sync_projection` | expose non-authoritative external/audit state |

## Resolver algorithm

```text
G4 merge evidence
→ bind merge_commit_sha
→ discover required workflows
→ resolve candidate workflow runs
→ reject runs whose head_sha != merge_commit_sha
→ group by workflow identity
→ select latest attempt per workflow
→ inspect jobs/artifacts/status
→ classify result
→ persist G5 evidence or checkpoint pending state
```

### Candidate run discovery order

1. Exact push lookup, when connector supports equivalent filters:
   - `event=push`
   - `branch=main`
   - `head_sha=<merge_commit_sha>`
2. Known `workflow_run_id` fallback from prior evidence.
3. Combined commit status/check-runs fallback for the same commit SHA.
4. `CONNECTOR_OBSERVABILITY_INCOMPLETE` when the connector cannot expose an exact run after the fallbacks above.

A PR-only run must not satisfy post-merge G5 unless it is explicitly recorded as a non-deployment informational check and is not used as main-branch post-merge evidence.

## Classification

| Classification | Required evidence | Runtime action |
|---|---|---|
| `success` | Every required workflow has a selected run for the exact merge SHA and terminal successful conclusion. | Record G5 PASS evidence. |
| `failure` | Any required workflow for the exact merge SHA has `failure`, `cancelled`, `timed_out`, or `action_required`. | Record blocker and route according to failure policy. |
| `CI_PENDING` | At least one exact merge-SHA run exists and is `queued`, `waiting`, `requested`, or `in_progress`. | Persist checkpoint and continuation. |
| `CONNECTOR_OBSERVABILITY_INCOMPLETE` | No exact run can be observed after exact lookup and fallback attempts. | Stop automatic pass; record connector gap. |
| `SHA_MISMATCH` | A candidate run exists but its head SHA does not equal the merge SHA. | Reject evidence and record blocker. |

## Pending checkpoint

Pending G5 must persist a checkpoint containing:

```yaml
checkpoint_type: g5-ci-status-verify
repository: owner/repo
merge_commit_sha: <sha>
required_workflows: []
observed_runs: []
selected_run_ids: []
status: pending
next_check_after: <ISO-8601 UTC>
continuation_mechanism: webhook | local_poll | scheduled_task | manual_checkpoint
attempt: 1
max_attempts: 20
```

The checkpoint must be resumed against the same repository, task, gate, merge SHA, and scope hash. A resumed run may not silently switch to a newer commit or latest workflow run.

## Evidence bundle

A successful G5 evidence artifact must conform to `schemas/g5-ci-verification-evidence.schema.json` and include:

- repository and merge commit SHA;
- required workflow identities;
- selected workflow run IDs and run attempts;
- job IDs, status, conclusion, and step summary when available;
- connector method used for discovery;
- rejected candidate reason when any candidate was rejected;
- final classification;
- timestamp and actor/runtime identity.

## Forbidden outcomes

```text
❌ latest green run without exact SHA binding
❌ PR-only run used as post-merge evidence without explicit classification
❌ empty run list reported as CI_PENDING
❌ pending state without checkpoint/continuation
❌ G5 status check used to deploy or reload runtime
❌ human bypass of failed CI, SHA mismatch, or missing required evidence
```

## Compatibility

This contract extends the current G5 exact-SHA language in `AGENTS.md`, `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`, and `core/E2E_DRAFT_PR_DELIVERY_RULE.md`. Existing G5 records remain valid when they already bind evidence to the exact merge commit. New G5 CI records should use the schema and checkpoint contract in this change.
