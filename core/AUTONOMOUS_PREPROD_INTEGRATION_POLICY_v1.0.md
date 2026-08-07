# Autonomous Pre-Prod Integration Policy v1.0

## Status

- Contract ID: `AUTONOMOUS_PREPROD_INTEGRATION_POLICY`
- Version: `1.0`
- Task: `SCRUM-272`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Autonomous integration target: `pre-prod`

## Purpose

Define bounded standing authority for one explicitly approved autonomous pre-production run. The contract can derive task-scoped G2 decisions and an exact-head standing G4 decision receipt without turning the parent approval into a reusable bearer token.

This task defines the policy, schemas and pure deterministic derivation layer. It does **not** activate a new live merge authority source. Existing live G4 gate-action validation remains on the trusted human receipt path until a later runtime task adds trusted repo-CI projection/readback for standing authority.

## Non-bypass invariants

1. `MODE_DOES_NOT_BYPASS_NODE_RUNTIME` remains mandatory.
2. `main` is never an autonomous integration target.
3. The only autonomous G4 target is `pre-prod`.
4. A child task risk above `R2` is denied.
5. A task outside the approved parent run manifest is denied.
6. Child G2 authority is bounded to one task, one working branch, one exact approved base SHA, declared paths/actions, the exact approved task risk, and expiry. A child request may not downgrade or upgrade its manifest-approved risk classification.
7. A parent run manifest is not trusted merely because its hashes are self-consistent. It must contain a trusted `github-actions[bot]` authority-receipt projection of the explicit parent approval.
8. The parent authority receipt binds approval ID, source comment, bot receipt comment, run ID, policy ID/revision/digest, immutable manifest approval-scope digest, scope prefix and expiry.
9. Standing G4 binds one PR number, current head SHA, task scope hash, PR-body digest, managed-block digest, graph digest, gate-story digest, evidence digest, parent authority digest and expiry.
10. Any drift in policy, manifest approval scope, parent authority, task scope, base/head, PR body, graph, story or evidence invalidates the decision.
11. A child autonomous task may not modify the standing policy, its schemas, validator/deriver, G4/G5 workflows, gate-action validator or gate lifecycle contract.
12. G5 remains read-only exact merge-SHA verification. This contract grants no deploy/release/runtime-reload authority.
13. G6 production data/configuration/credential/secret/migration authority is not applicable and is never granted.

## Parent run approval trust model

The closed parent run manifest contains `authority_receipt` with this trusted projection identity:

```text
status = present
source = github_actions_bot_comment
bot_login = github-actions[bot]
marker = gwc:autonomous-preprod-run-authority-receipt
approval_id
receipt_comment_id
source_comment_id
approved_run_id
approved_policy_id
approved_policy_revision
approved_policy_digest
manifest_scope_digest
scope_hash_prefix
issued_at
expires_at
```

`manifest_scope_digest` is SHA-256 over canonical manifest JSON with `authority_receipt` removed. This avoids a circular digest and makes any post-approval change to task allowlists, base, target, policy binding, expiry or idempotency key invalidate the parent receipt.

The pure validator models and validates this trusted readback shape. A later live issuer must obtain the receipt from repository/GitHub evidence; an agent-authored object that merely copies the field names is not sufficient operational evidence.

## Canonical digest rules

All deterministic digests use UTF-8 JSON, lexicographically sorted object keys, preserved array order, no insignificant whitespace and SHA-256.

- `policy_digest`: complete policy document.
- `manifest_approval_scope_digest`: run manifest with `authority_receipt` removed.
- `authority_receipt_digest`: complete parent authority receipt.
- `manifest_digest`: complete approved manifest including authority receipt.
- task `scope_hash`: task object with `scope_hash` removed.
- decision `decision_digest`: decision object with `decision_digest` removed.

Unchanged inputs replay to identical digests.

## Child G2 derivation

An allowlisted child G2 request may derive only these lifecycle actions when present in the approved task scope:

```text
create_guarded_branch_or_worktree
modify_approved_files
run_sandboxed_validation
stage
create_commit
push_working_branch
```

Eligibility requires current policy + approved parent manifest, trusted parent authority receipt, exact approved base SHA, matching `auto/` working branch, **request risk exactly equal to the manifest-approved task risk**, requested paths/actions contained by the task allowlist, and no protected control-plane overlap. Any attempted risk downgrade or upgrade is `AUTONOMOUS_SCOPE_DRIFT` and fails closed.

The output carries `parent_approval_id`, `parent_scope_hash_prefix` and `parent_authority_digest`. It explicitly sets `g4_g5_g6_authority_granted: false`.

## Standing G4 decision receipt

The pure deriver may produce `autonomous-preprod-g4-receipt` only for an approved allowlisted task and exact `pre-prod` context. It binds:

```text
policy id/revision/digest
manifest digest
parent approval id
parent scope hash prefix
parent authority digest
run id
task id
task scope hash
repository
pre-prod target
PR number
current head SHA
PR body digest
managed block digest
run graph digest
gate story digest
evidence digest
merge_approved_pr
expiry
decision digest
```

The receipt includes:

```text
trust_state = requires_trusted_repo_ci_projection
```

That state is deliberate. In SCRUM-272 the receipt is a deterministic **contract decision**, not a live merge credential. The existing `gate-action-authority` schema, validator and regression tests remain byte-compatible with `main`; they do not accept this standing receipt as a replacement for the trusted human G4 receipt.

A later runtime integration must independently read the approved parent receipt and current PR evidence, then project/attest standing authority through trusted repository CI before a live merge gate can consume it.

## Fail-closed reason codes

At minimum:

```text
AUTONOMOUS_POLICY_INVALID
AUTONOMOUS_POLICY_EXPIRED
AUTONOMOUS_POLICY_REVISION_DRIFT
AUTONOMOUS_POLICY_DIGEST_DRIFT
AUTONOMOUS_RUN_MANIFEST_INVALID
AUTONOMOUS_RUN_MANIFEST_EXPIRED
AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED
AUTONOMOUS_TASK_NOT_ALLOWLISTED
AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING
AUTONOMOUS_MAIN_TARGET_FORBIDDEN
AUTONOMOUS_PREPROD_TARGET_REQUIRED
AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN
AUTONOMOUS_ACTION_FORBIDDEN
AUTONOMOUS_SCOPE_DRIFT
AUTONOMOUS_BASE_SHA_MISMATCH
AUTONOMOUS_HEAD_DRIFT
AUTONOMOUS_PR_BODY_DRIFT
AUTONOMOUS_GRAPH_DRIFT
AUTONOMOUS_STORY_DRIFT
AUTONOMOUS_EVIDENCE_DRIFT
AUTONOMOUS_STANDING_G4_RECEIPT_INVALID
```

## Explicit exclusions

This contract does not create/protect `pre-prod`, choose arbitrary Jira work, invoke an AI coding adapter, create a trusted parent authority receipt by itself, project standing authority into the live G4 gate, merge a PR, deploy, release, reload runtime, mutate production configuration/data, rotate credentials, handle secrets or run migrations.
