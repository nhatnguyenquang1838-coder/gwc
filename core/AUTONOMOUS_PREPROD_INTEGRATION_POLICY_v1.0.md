# Autonomous Pre-Prod Integration Policy v1.0

## Status

- Contract ID: `AUTONOMOUS_PREPROD_INTEGRATION_POLICY`
- Version: `1.0`
- Task: `SCRUM-272`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Autonomous integration target: `pre-prod`

## Purpose

Define bounded standing authority for one explicitly approved autonomous pre-production run. The contract can derive task-scoped G2 decisions and an exact-head standing G4 decision receipt without turning the parent approval into a reusable bearer token.

The autonomous route is:

```text
AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN
```

`main` is governance/release/promotion context. Exact remote `pre-prod` is the autonomous execution/integration base for child tasks. Human G4 remains mandatory for `pre-prod -> main` promotion.

## Non-bypass invariants

1. `MODE_DOES_NOT_BYPASS_NODE_RUNTIME` remains mandatory.
2. `main` is never an autonomous child integration target.
3. The only autonomous child G4 target is `pre-prod`.
4. A child task risk above `R2` is denied.
5. A task outside the approved parent run manifest is denied.
6. DAG readiness is dependency eligibility only. A task MUST NOT be claimed until trusted/current parent authority has been resolved and the task is explicitly allowlisted. Runtime state therefore distinguishes `READY_FOR_AUTHORITY` from `AUTHORIZED_READY`.
7. Child G2 authority is bounded to one task, one canonical `auto/` working branch, one exact approved base SHA, declared paths/actions, exact approved task risk, and expiry.
8. A parent run manifest is not trusted merely because its hashes are self-consistent. It must contain a trusted `github-actions[bot]` authority-receipt projection of the explicit parent approval.
9. The parent authority receipt binds approval ID, distinct source/receipt comments, run ID, policy ID/revision/digest, immutable manifest approval-scope digest, exact first-16 scope prefix and expiry.
10. Standing G4 binds repository, approved base ref/SHA, exact approved child branch, `pre-prod` target, `merge_approved_pr`, PR number, current head SHA, task scope hash, PR/evidence digests, parent authority digest and expiry.
11. Any drift in policy, manifest approval scope, parent authority, task scope, repository, base, branch, head, target/action, PR body, graph, story or evidence invalidates the decision.
12. **Node Architect implementation is not blanket control-plane self-modification.** Task-scoped changes under `core/node-architect/**`, `schemas/node-architect/**`, `tools/node_architect/**`, and matching tests MAY be authorized when explicitly present in the immutable parent manifest and within the task risk/action bounds.
13. The current run MUST NOT modify the **exact active authority plane** used to authorize or enforce that same run. The manifest may bind `immutable_authority_paths`; overlap with those exact paths fails closed with `AUTONOMOUS_ACTIVE_AUTHORITY_SELF_MODIFICATION_FORBIDDEN`.
14. Legacy manifests that do not yet carry `immutable_authority_paths` use the validator's exact-file compatibility set for active authority issuers/validators. Compatibility MUST NOT fall back to blanket directory prefixes such as `core/node-architect`, `schemas/node-architect`, or `tools/node_architect`.
15. The broader `control_plane_protected_paths` policy list remains a defense/governance inventory and policy integrity requirement. It MUST NOT by itself be interpreted as the current run's immutable authority-plane overlap set.
16. Policy, manifest and parent authority timestamps are activation boundaries, not metadata only. Future/expired objects fail closed.
17. Repository paths and working branch refs are canonicalized. Traversal/root aliases, control characters, backslashes/globs and malformed Git refs fail closed.
18. G5 remains read-only exact merge-SHA verification. This contract grants no deploy/release/runtime-reload authority.
19. G6 production data/configuration/credential/secret/migration authority is not applicable and is never granted.

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

The manifest MAY additionally carry:

```text
immutable_authority_paths[]
```

These are the exact repository-relative files/directories constituting the active authority plane for that approved run. They are part of the manifest approval-scope digest and therefore cannot be changed after approval without invalidating the parent receipt.

`manifest_scope_digest` is SHA-256 over canonical manifest JSON with `authority_receipt` removed. This avoids a circular digest and makes any post-approval change to task allowlists, immutable authority paths, base, target, policy binding, expiry or idempotency key invalidate the parent receipt. `scope_hash_prefix` must equal the first 16 hexadecimal characters of that digest. The source approval comment and bot receipt comment must be distinct.

The pure validator models this trusted readback shape. A live issuer must obtain the receipt from repository/GitHub evidence; an agent-authored object that merely copies the field names is not operational authority.

## Canonical digest rules

All deterministic digests use UTF-8 JSON, lexicographically sorted object keys, preserved array order, no insignificant whitespace and SHA-256.

- `policy_digest`: complete policy document.
- `manifest_approval_scope_digest`: run manifest with `authority_receipt` removed.
- `authority_receipt_digest`: complete parent authority receipt.
- `manifest_digest`: complete approved manifest including authority receipt.
- task `scope_hash`: task object with `scope_hash` removed.
- decision `decision_digest`: decision object with `decision_digest` removed.

Unchanged inputs replay to identical digests.

## Autonomous task selection and claim

The closed-loop runtime MUST use this order:

```text
DAG_SELECT
→ AUTHORITY_RESOLVE
→ BASE_REFRESH
→ CLAIM
→ EXECUTE
```

A task that satisfies dependencies but lacks valid parent authority is `READY_FOR_AUTHORITY`; it is not claimable. Once trusted/current authority is valid and the task is allowlisted, it becomes `AUTHORIZED_READY`. Only `AUTHORIZED_READY` may emit the Jira/GitHub CAS claim action.

A downstream task MUST NOT dispatch while any declared predecessor is not terminal-complete (`COMPLETED` or `G5_VERIFIED` under the runtime contract). Jira `Done` text alone is not sufficient when the canonical DAG snapshot does not classify the predecessor as terminal-complete.

## Child G2 derivation

An allowlisted child G2 request may derive only lifecycle actions present in the approved task scope, including:

```text
create_guarded_branch_or_worktree
modify_approved_files
run_sandboxed_validation
stage
create_commit
push_working_branch
```

Eligibility requires current policy + approved parent manifest, trusted parent authority receipt, exact approved execution base, matching canonical `auto/` branch, request risk equal to the manifest-approved task risk, requested paths/actions contained by the task allowlist, and no overlap with the active immutable authority plane.

Requested path/action arrays must be non-empty, unique string arrays. Malformed/nested/duplicate request arrays fail closed.

All policy-protected, immutable-authority and task-authorized paths must be canonical repository-relative POSIX paths. Absolute paths, leading/trailing whitespace, control characters, backslashes, empty path segments, `.`/`..` segments and glob metacharacters are forbidden.

Working branch refs must be canonical Git refs under `auto/`: protected/special refs, `..`, `@{`, repeated separators, control/whitespace characters, forbidden Git ref characters, dot-prefixed components and `.lock` components fail closed.

The output carries parent authority provenance, explicitly sets later authority as not granted, and remains a bounded deterministic decision. Trusted repository/CI projection is still required wherever the live runtime contract requires it.

## Standing G4 decision receipt

The pure deriver may produce `autonomous-preprod-g4-receipt` only for an approved allowlisted task and exact current context. It binds policy/manifest/parent authority, run/task/scope, repository/base/branch, `pre-prod` target, PR/head, managed evidence, graph/story/evidence digests, expiry and decision digest.

A receipt cannot be replayed in another repository, against another base, from another branch, against `main`, or for a non-merge action merely because its self-computed digest remains internally consistent.

The standing receipt is evidence/decision data, not a bearer credential for unrelated gates. Human authority remains required for promotion/merge to `main`.

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
AUTONOMOUS_TASK_NOT_READY
AUTONOMOUS_TASK_RISK_EXCEEDS_CEILING
AUTONOMOUS_MAIN_TARGET_FORBIDDEN
AUTONOMOUS_PREPROD_TARGET_REQUIRED
AUTONOMOUS_ACTIVE_AUTHORITY_SELF_MODIFICATION_FORBIDDEN
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

`AUTONOMOUS_CONTROL_PLANE_SELF_MODIFICATION_FORBIDDEN` is a legacy coarse classification and MUST NOT be emitted for ordinary Node Architect implementation merely because a path is under a Node Architect directory.

## Explicit exclusions

This contract does not create/protect `pre-prod`, choose arbitrary out-of-lane Jira work, create a trusted parent authority receipt by itself, merge a child PR to `main`, deploy, release, reload runtime, mutate production configuration/data, rotate credentials, handle secrets or run migrations.
