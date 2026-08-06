# Autonomous Pre-Prod Runtime Contract v0.1

## Status

- Contract ID: `autonomous-preprod-runtime`
- Version: `0.1`
- Task: `SCRUM-271`
- Lifecycle: `experimental`
- Repository: `nhatnguyenquang1838-coder/gwc`

## Purpose

Define the first executable vertical slice for an AI-managed workflow that can
materialize one run-scoped Node Architect graph, tell the factual G0→G6 story,
and place exact-head evidence into a bounded Pull Request description section.

This version is evidence/control-plane only. It does **not** implement arbitrary
Jira task selection, AI implementation-agent execution, standing-policy G4
authority, `pre-prod` branch creation, PR creation, merge, deploy, release,
runtime reload, production configuration, credential/secret work, migration,
or production-data access.

## Invariants

1. `MODE_DOES_NOT_BYPASS_NODE_RUNTIME`.
2. `main` is a terminally forbidden autonomous PR target.
3. Graph JSON is canonical; Mermaid and prose are deterministic projections.
4. Only canonical runtime events may create graph participants.
5. Gate actions are rendered as `gate_action`, never as invented catalogue nodes.
6. `not_executed` and `not_applicable` are explicit states and never implicit PASS.
7. G4 evidence must bind current PR head, PR-body digest, graph digest, story
   digest, and managed-evidence digest.
8. Any head, body, graph, story, scope, policy, or evidence drift invalidates
   prior G4 readiness.
9. Updating a PR description is evidence assembly; it never grants G4 authority.
10. G5 and G6 authority remain separate. G6 is `not_applicable` for this slice.

## Canonical inputs

The evidence-only runtime consumes a JSON manifest containing:

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

Each event must carry a unique `event_id` and `sequence`, one canonical gate,
participant type (`runtime_node` or `gate_action`), canonical participant ID,
purpose, entry evidence, action, outcome, output evidence, route provenance, and
optional next event.

## Canonical outputs

```text
runtime-result.json
runtime-graph.json
gate-story.json
pr-run-evidence.md
updated-pr-body.md
```

The graph and story are closed-schema artifacts. The PR evidence block uses:

```markdown
<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:BEGIN -->
<!-- gwc:autonomous-run-evidence ... -->
...
<!-- GWC:AUTONOMOUS-RUN:EVIDENCE:END -->
```

Human-authored PR content outside this block must be preserved byte-for-byte
except for the newline required to append the first managed block.

## G4 evidence binding

For autonomous-run PRs, a valid G4 path requires both:

1. the existing trusted `gwc:g4-authority-receipt`; and
2. a trusted `gwc:g4-pr-evidence-receipt` generated after readback of the current
   PR body and current PR head.

The second receipt binds:

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

A new commit or PR-body edit makes the prior receipt stale. The workflow must
re-read current state rather than selecting any historical matching comment.

## Fail-closed reason codes

```text
AUTONOMOUS_MAIN_TARGET_FORBIDDEN
AUTONOMOUS_MANIFEST_INVALID
AUTONOMOUS_GRAPH_INPUT_INVALID
AUTONOMOUS_GRAPH_EVENT_MISSING
AUTONOMOUS_GRAPH_EVENT_DUPLICATE
AUTONOMOUS_GRAPH_ROUTE_TARGET_MISSING
AUTONOMOUS_PR_MARKER_MALFORMED
AUTONOMOUS_PR_EVIDENCE_MISSING_OR_MALFORMED
AUTONOMOUS_PR_EVIDENCE_MARKER_INVALID
AUTONOMOUS_PR_HEAD_DRIFT
AUTONOMOUS_PR_EVIDENCE_DRIFT
G4_PR_EVIDENCE_RECEIPT_MISSING_OR_STALE
```

## Acceptance boundary for v0.1

A deterministic fixture must produce schema-valid graph/story artifacts,
idempotently update a PR body, render only actual participants, explain G0→G6,
and block `main`, malformed markers, missing events, unknown route targets, and
stale G4 evidence. No external side effect is required to demonstrate this
contract.
