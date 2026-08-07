# Autonomous Pre-Prod Runtime Contract v0.1

## Status

- Contract ID: `autonomous-preprod-runtime`
- Version: `0.1`
- Origin task: `SCRUM-271`
- Standing-policy extension: `SCRUM-272`
- Lifecycle: `experimental`
- Repository: `nhatnguyenquang1838-coder/gwc`

## Purpose

Define the evidence/control-plane vertical slice that materializes one run-scoped Node Architect graph, tells the factual G0→G6 story, and places exact-head evidence into a bounded Pull Request description section.

This runtime does **not** implement arbitrary Jira task selection, AI implementation-agent execution, `pre-prod` branch creation/protection, PR creation, merge, deploy, release, runtime reload, production configuration, credential/secret work, migration, or production-data access.

`SCRUM-272` adds a separate `AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0` contract. That policy can derive task-scoped standing decisions, but this evidence runtime does not mint or broaden live merge authority.

## Invariants

1. `MODE_DOES_NOT_BYPASS_NODE_RUNTIME`.
2. `main` is a terminally forbidden autonomous PR target.
3. Graph JSON is canonical; Mermaid and prose are deterministic projections.
4. Only canonical runtime events may create graph participants.
5. Gate actions are rendered as `gate_action`, never as invented catalogue nodes.
6. `not_executed` and `not_applicable` are explicit states and never implicit PASS.
7. G4 evidence binds current PR head, PR-body digest, graph digest, story digest and managed-evidence digest.
8. Any head, body, graph, story, scope, policy or evidence drift invalidates prior G4 readiness.
9. Updating a PR description is evidence assembly; it never grants G4 authority.
10. G5 and G6 authority remain separate. G6 is `not_applicable` for this slice.
11. Manifest repository and `base_sha` must match the exact repository and source SHA selected by the workflow before artifacts are accepted.
12. Explicit gate-status metadata may only restate canonical event outcomes; it may never override a blocked or absent execution state.
13. The additional PR-evidence receipt applies only to autonomous-run G4 flows; normal/legacy G4 delivery retains its existing authority-receipt contract.
14. A standing-policy decision is not a live authority receipt until trusted repository CI independently projects/attests it from an approved parent-run receipt and current PR evidence.

## Evidence-runtime input

The SCRUM-271 evidence runtime consumes a JSON manifest containing:

```text
run_id
task_id
repository
base_ref
base_sha
head_ref
head_sha
pr_base
graph_revision
events[]
gate_statuses
validation
g4_readiness
```

Each event carries a unique `event_id` and `sequence`, canonical gate, participant type (`runtime_node` or `gate_action`), canonical participant ID, purpose, entry evidence, action, outcome, output evidence, route provenance and optional next event.

The parent standing-policy run manifest is a separate closed artifact defined by `schemas/autonomous-preprod-run-manifest.schema.json`; it is not interchangeable with this event manifest.

## Canonical evidence outputs

```text
runtime-result.json
runtime-graph.json
gate-story.json
pr-run-evidence.md
updated-pr-body.md
```

The managed PR evidence block uses:

```markdown
<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:BEGIN -->
<!-- gwc:autonomous-run-evidence ... -->
...
<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:END -->
```

Human-authored PR content outside this block is preserved. Before update, the rendered marker head must equal the current PR head; readback confirms both body and head.

## Current live G4 evidence binding

For an autonomous-run PR on the currently active live gate path, G4 requires:

1. the existing trusted PR-native human `gwc:g4-authority-receipt`; and
2. the trusted current `gwc:g4-pr-evidence-receipt` generated after readback of the current PR body and head.

The PR-evidence receipt binds:

```text
pr_number
approved_head_sha
pr_body_digest
managed_block_digest
run_graph_digest
gate_story_digest
evidence_digest
source_comment_id
expiry
```

A new commit or PR-body edit makes prior evidence stale.

Normal/legacy PRs continue to require the existing trusted human G4 authority receipt only.

## Standing-policy extension boundary

`SCRUM-272` defines a deterministic standing G4 **decision receipt** bound to an approved parent run and current PR evidence. It carries `trust_state=requires_trusted_repo_ci_projection`.

It intentionally does not alter the live `gate-action-authority` schema or validator. A later runtime task may replace the per-task human G4 authority source only after it provides an independently trusted repo-CI projection/readback of:

- the parent human approval receipt;
- immutable manifest approval-scope digest;
- policy revision/digest;
- task scope;
- exact PR/head/body/graph/story/evidence state; and
- receipt expiry.

Until that integration exists, a caller-computable standing decision digest is never sufficient merge authority.

## Fail-closed reason codes

```text
AUTONOMOUS_MAIN_TARGET_FORBIDDEN
AUTONOMOUS_MANIFEST_INVALID
AUTONOMOUS_REPOSITORY_BINDING_MISMATCH
AUTONOMOUS_BASE_SHA_MISMATCH
AUTONOMOUS_GRAPH_INPUT_INVALID
AUTONOMOUS_GRAPH_EVENT_MISSING
AUTONOMOUS_GRAPH_EVENT_DUPLICATE
AUTONOMOUS_GRAPH_ROUTE_TARGET_MISSING
AUTONOMOUS_GATE_STATUS_INVALID
AUTONOMOUS_GATE_STATUS_CONFLICT
AUTONOMOUS_PR_MARKER_MALFORMED
AUTONOMOUS_PR_EVIDENCE_MISSING_OR_MALFORMED
AUTONOMOUS_PR_EVIDENCE_MARKER_INVALID
AUTONOMOUS_PR_HEAD_DRIFT
AUTONOMOUS_PR_EVIDENCE_DRIFT
G4_PR_EVIDENCE_RECEIPT_MISSING_OR_STALE
AUTONOMOUS_RUN_AUTHORITY_UNTRUSTED
AUTONOMOUS_STANDING_G4_RECEIPT_INVALID
```

## Acceptance boundary

The evidence runtime must remain deterministic and side-effect bounded. The standing-policy extension must preserve the existing live human G4 trust boundary while defining a closed, replayable, parent-approved decision contract for later trusted runtime integration.
