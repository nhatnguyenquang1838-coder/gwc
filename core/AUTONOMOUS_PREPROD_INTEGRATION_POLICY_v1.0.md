# Autonomous Pre-Prod Integration Policy v1.0

## Status

- Contract ID: `AUTONOMOUS_PREPROD_INTEGRATION_POLICY`
- Version: `1.0`
- Task: `SCRUM-272`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Target integration branch: `pre-prod`

## Purpose

This contract defines bounded standing authority for one already-approved autonomous pre-production run. It allows the run to derive task-scoped G2 execution authority and an exact-head G4 merge authority receipt without asking for a new human command between every allowlisted task.

The parent run is not a bearer token. Every child decision is recomputed from the current policy, parent manifest, task allowlist, exact base/head and current evidence.

## Non-bypass invariants

1. `MODE_DOES_NOT_BYPASS_NODE_RUNTIME` remains mandatory.
2. `main` is never an autonomous integration target.
3. The only autonomous G4 target is `pre-prod`.
4. A child task risk above `R2` is denied.
5. A task outside the parent manifest allowlist is denied.
6. Child G2 authority is bounded to one task, one working branch, one exact protected-base SHA, declared paths/actions, risk and expiry.
7. Standing G4 authority binds one PR number, current head SHA, task scope hash, PR-body digest, managed-block digest, graph digest, gate-story digest, evidence digest, policy revision and expiry.
8. Any drift in policy, manifest, task scope, base/head, PR body, graph, story or evidence invalidates the prior decision or receipt.
9. The runtime may not modify the policy, its schemas, validator/deriver, G4/G5 workflows, gate-action validator or gate lifecycle contract inside a child autonomous task scope.
10. G5 is read-only exact merge-SHA verification. This contract grants no deploy/release/runtime-reload authority.
11. G6 production data/configuration/credential/secret/migration authority is not applicable and is never granted.

## Canonical artifacts

```text
governance/autonomous-preprod-policy.yaml
schemas/autonomous-preprod-run-policy.schema.json
schemas/autonomous-preprod-run-manifest.schema.json
schemas/autonomous-preprod-g4-receipt.schema.json
```

The policy and manifest are closed-schema documents. Unknown fields fail validation.

## Canonical digest rules

All deterministic digests use:

```text
UTF-8 JSON
keys sorted lexicographically
array order preserved
no insignificant whitespace
SHA-256
```

- `policy_digest` is computed over the complete policy document.
- `manifest_digest` is computed over the complete run manifest.
- each task `scope_hash` is computed over that task object with `scope_hash` removed;
- each derived decision or receipt `decision_digest` is computed over the output object with `decision_digest` removed.

Unchanged inputs therefore replay to the same digest.

## Child G2 derivation

A child G2 request is eligible only when all of the following are current and valid:

- policy and run manifest schemas pass;
- policy and run manifest are unexpired;
- manifest policy id/revision/digest match the active policy;
- repository and target branch match;
- exact observed base SHA equals the parent approved base SHA;
- task is allowlisted;
- task risk is within the policy ceiling;
- requested working branch matches the manifest and policy prefix;
- requested paths/actions are within the allowlisted task scope;
- no requested path overlaps the protected control plane;
- no denied action is requested.

The derived child authority never contains G4, G5 or G6 authority.

## Standing G4 receipt

Standing G4 replaces only the per-task human G4 authority receipt for eligible autonomous `pre-prod` tasks. It does not replace SCRUM-271 current PR-evidence binding.

An autonomous merge therefore still requires the current `g4-pr-evidence-receipt` plus a valid `autonomous-preprod-g4-receipt`.

The standing receipt is `ALLOW` only when:

- current PR base is exactly `pre-prod`;
- task is allowlisted and within risk ceiling;
- current head SHA is supplied;
- task scope hash matches the parent manifest;
- PR body, managed block, graph, story and evidence digests are supplied in canonical SHA-256 form;
- policy and manifest remain current and unexpired.

A receipt does not authorize any other PR, task, branch, head or action.

## Compatibility

Normal/legacy delivery keeps the existing human `gwc:g4-authority-receipt` path. The gate-action validator accepts standing policy only as an alternative authority source for an autonomous pre-prod merge; existing human G4 packets remain valid without a standing-policy artifact.

## Fail-closed reason codes

At minimum:

```text
AUTONOMOUS_POLICY_INVALID
AUTONOMOUS_POLICY_EXPIRED
AUTONOMOUS_POLICY_REVISION_DRIFT
AUTONOMOUS_POLICY_DIGEST_DRIFT
AUTONOMOUS_RUN_MANIFEST_INVALID
AUTONOMOUS_RUN_MANIFEST_EXPIRED
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

This v1.0 contract does not create or protect `pre-prod`, choose arbitrary Jira work, invoke an AI coding adapter, merge a live PR by itself, deploy, release, reload runtime, mutate production configuration/data, rotate credentials, handle secrets or run migrations.
