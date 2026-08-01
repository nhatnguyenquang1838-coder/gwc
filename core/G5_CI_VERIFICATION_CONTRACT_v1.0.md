# G5 CI Verification Contract v1.0

## Purpose

This contract defines the read-only G5 status-verification runtime for GitHub Actions after a G4 merge. It turns the existing exact-SHA rule into an executable resolver, evidence bundle, and checkpoint protocol.

The local implementation is split into `tools/resolve_g5_status.py`, which
normalizes connector-provided candidates without making connector calls, and
`tools/validate_g5_status.py`, which validates the resulting
`schemas/g5-status-evidence.schema.json` artifact. The resolver is not a
workflow runner and cannot create, merge, deploy, or reload anything.

G5 CI verification is not a deployment authority. It never permits merge, deploy, release, publish, runtime reload, production configuration, credentials, secrets, migrations, or production-data operations.

## Scope

```text
Gate: G5_DEPLOY
Default action: G5_STATUS_VERIFY
Authority: automatic read-only after G4 merge
Manual G5 approval: required only for manual deploy/redeploy/release/publish/runtime reload
```

## G4-to-G5 evidence chain

The following evidence sources are deliberately separate:

```text
Human G4 PR comment
→ validated G4 authority receipt
→ GitHub pull_request.closed merge event
→ G4 merge-proof artifact/comment
→ exact merge-SHA post-merge workflow observation
→ canonical G5 Actions artifact
→ G5 PR trace comment
→ optional Jira/Slack projections
```

Authority rules:

- The original human PR comment containing the exact G4 approval command is the merge authority.
- The bot-generated `gwc:g4-authority-receipt` comment is a sanitized receipt; it does not create authority.
- The GitHub `pull_request.closed` event with `merged=true` is merge proof.
- G4 approval evidence never satisfies G5. G5 starts only after a merge commit exists and exact-SHA post-merge evidence is observed.
- The GitHub Actions artifact is canonical machine evidence for G5.
- The `gwc:g5-status` PR comment is human traceability only.
- Jira and Slack are `projection_only`; they never replace the GitHub authority, merge event, or Actions artifact.
- Evidence is never committed back to the merged branch and never delivered through a recursive evidence PR.

The executable workflow is `.github/workflows/g4-g5-evidence.yml`.
It validates G4 comment authority, records merge proof, observes the required
post-merge workflows for the exact merge SHA, uploads the canonical G5 artifact,
and updates the PR trace comment. It does not invoke merge, deploy, release,
publish, runtime reload, repository write, branch creation, or Pull Request
creation APIs.

## Required G4 authority receipt

Before merge, a G4 authority receipt must validate against:

```text
schemas/g4-merge-authority-receipt.schema.json
tools/validate_g4_merge_authority.py
```

The receipt must bind:

- repository and PR number;
- exact current Ready-for-Review head SHA;
- G4 approval ID and scope-hash prefix;
- original human PR comment ID and URL;
- approver identity with `write`, `maintain`, or `admin` permission;
- issue and expiry timestamps;
- authorized action `merge_pull_request` only;
- `manual_g5_action_authorized: false`.

A Draft PR, expired command, unauthorized commenter, changed head SHA, or
malformed command fails closed.

## Required merge proof

After merge, GitHub event evidence must bind:

```text
provider: github
event: pull_request.closed
merged: true
approved_head_sha: <G4 exact head>
merged_head_sha: <PR head at merge>
merge_commit_sha: <GitHub merge commit>
exact_head_match: true
```

If the approved head and merged head differ, G4 evidence is stale and the chain
is invalid. The merge event is proof of what GitHub merged; it is not a G5 PASS.

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
| G4 authority and merge SHA binding | `repo_delivery` | bind human authority, merged head, merge event, and commit identity |
| pending state persistence | `runtime_checkpoint` | persist and resume same SHA |
| failure classification | `failure_recovery` | route failed/cancelled/timeout states |
| evidence quality | `validation_quality` | reject stale, neutral, skipped, unrelated, or authority-incomplete checks |
| audit projection | `sync_projection` | link the canonical artifact and PR comment to non-authoritative external projections |

## Resolver algorithm

```text
G4 authority receipt
→ GitHub merge event
→ bind merge_commit_sha
→ discover required workflows
→ resolve candidate workflow runs
→ reject runs whose head_sha != merge_commit_sha
→ group by workflow identity
→ select latest attempt per workflow
→ inspect jobs/artifacts/status
→ classify result
→ persist G5 Actions artifact or checkpoint pending state
→ update G5 PR trace comment
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
| `success` | Every required workflow has a selected run for the exact merge SHA and terminal successful conclusion. | Upload canonical G5 artifact and update PR trace comment. |
| `failure` | Any required workflow for the exact merge SHA has `failure`, `cancelled`, `timed_out`, or `action_required`. | Upload blocker evidence and route according to failure policy. |
| `CI_PENDING` | At least one exact merge-SHA run exists and is `queued`, `waiting`, `requested`, or `in_progress`. | Persist checkpoint artifact and continue on the next required `workflow_run` completion. |
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

If no exact-SHA run can be observed, the resolver must retain the discovery
attempt and fallback list and classify the result as
`CONNECTOR_OBSERVABILITY_INCOMPLETE`. It must never turn an empty result into
`CI_PENDING` or select the latest green run by recency alone.

## Evidence bundle

A successful G5 evidence artifact must conform to `schemas/g5-ci-verification-evidence.schema.json` and include:

- repository and merge commit SHA;
- G4 authority comment reference and approved head SHA;
- GitHub merge-event proof and exact approved-head/merged-head match;
- required workflow identities;
- selected workflow run IDs and run attempts;
- job IDs, status, conclusion, and step summary when available;
- connector method used for discovery;
- rejected candidate reason when any candidate was rejected;
- final classification;
- canonical GitHub Actions artifact name and workflow run ID;
- PR trace-comment marker;
- Jira/Slack `projection_only` declaration;
- `no_recursive_evidence_pr: true`;
- timestamp and actor/runtime identity.

## Human-authorized bootstrap recovery

Bootstrap recovery is permitted only when a merged PR could not have emitted the normal G4/G5 receipt chain because it introduced or activated that chain itself. Recovery extends `.github/workflows/g4-g5-evidence.yml`; it is not a parallel governance system.

The exact human command is attached to the immutable merged PR:

```text
APPROVE G5 RECOVERY <recovery_id> <owner/repo> <pr_number> <g4_approval_id> <scope_hash_16> <approved_head_sha> <merge_commit_sha> <validate_run_id> <build_run_id> <source_authority_sha256> <expires_at_utc>
```

Before evidence materialization, the workflow must verify the repository/PR context, current approver permission, expiry, merged PR state, exact head and merge SHA, original G4 approval/head provenance in the merge commit message, and the exact successful `push:main` run IDs for `Validate instructions` and `Build instruction packages`. The external governed-chat receipt is bound by its SHA-256 digest.

Recovery evidence must validate against `schemas/g5-recovery-authority.schema.json` with `tools/validate_g5_recovery_authority.py`, carry `recovery_mode: bootstrap_manual_authority`, upload a canonical GitHub Actions artifact, and publish sanitized `gwc:g5-recovery-authority`, recovered `gwc:g4-merge-proof`, and recovered `gwc:g5-status` comments.

Exact duplicates are idempotent no-ops. Conflicting trusted receipts for the same PR and merge SHA fail closed. Recovery must state that historical events were not rewritten and must never claim the original automated event ran.

Recovery authorizes evidence materialization only. It never authorizes merge, deploy, redeploy, release, publish, runtime reload, production configuration/data, credentials, secrets, migration, force-push, branch deletion, or a recursive evidence PR.

## Forbidden outcomes

```text
❌ bot receipt treated as the original G4 authority
❌ merge without exact Ready-for-Review head binding
❌ G4 receipt treated as G5 PASS
❌ latest green run without exact SHA binding
❌ PR-only run used as post-merge evidence without explicit classification
❌ empty run list reported as CI_PENDING
❌ pending state without checkpoint/continuation
❌ PR comment treated as canonical G5 machine evidence
❌ Jira or Slack projection treated as authority
❌ recursive evidence commit or evidence PR
❌ G5 status check used to deploy or reload runtime
❌ human bypass of failed CI, SHA mismatch, or missing required evidence
❌ recovery without exact human authority and immutable merged-PR bindings
❌ recovery that hides or rewrites its provenance
```

## Compatibility

This contract extends the current G4/G5 exact-SHA language in `AGENTS.md`, `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`, and `core/E2E_DRAFT_PR_DELIVERY_RULE.md`. Existing G5 records remain valid when they already bind evidence to the exact merge commit. New event-driven G5 records should include the additive `evidence_chain` object and use the schema, workflow, and checkpoint contract in this change. Bootstrap recovery is additive and does not change the normal event-driven path or the 81-node runtime catalog.
