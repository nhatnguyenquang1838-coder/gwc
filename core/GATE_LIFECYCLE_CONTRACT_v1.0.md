# GWC Gate Lifecycle Contract v1.1

## Purpose

This contract defines the required entry evidence, permitted actions, exit evidence, and authority boundary for G0 through G6. It extends the existing G0/G1 artifact lifecycle without replacing it.

## Gate sequence

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ G4_MERGE
→ G5_DEPLOY (status check unless manual deploy is explicitly in scope)
→ G6_PRODUCTION_DATA (only when applicable)
```

A later gate never implies authority for another gate. Every gate fails closed when required evidence is missing, invalid, expired, contradictory, or scoped to a different repository, task, base SHA, branch, or scope hash.

## Enforcement model

GWC enforcement has three layers:

1. **Repository contract** — schemas, templates, validators, tests, and CI.
2. **Agent runtime contract** — an agent must validate the requested action before invoking a write-capable connector.
3. **Platform control** — branch protection, required checks, deployment environments, and production access controls.

Repository controls cannot by themselves intercept an external connector call. Connector-level hard blocking therefore requires the runtime to invoke `tools/validate_gate_action.py` before the action. CI remains a second, independent fail-closed boundary.

## Canonical evidence workspace

Each task uses an isolated workspace:

```text
.gwc/tasks/<task-id>/
├── g0/context-snapshot.yaml
├── g1/intake/g1-intake-brief.yaml
├── g1/preflight/g1-preflight-report.yaml
├── g1/brainstorming/g1-options.yaml
├── g1/decision/g1-decision-record.yaml
├── g2/execution-envelope.yaml
├── g3/delivery-record.yaml
├── g4/merge-approval.yaml
├── g5/deployment-approval.yaml
└── g6/production-approval.yaml
```

The existing single-task `.gwc/g0` and `.gwc/g1` layout remains supported for backward compatibility. New concurrent work should use the task-scoped layout.

### Required artifact matrix

The task workspace is the source of truth for gate applicability and evidence:

| Gate | Artifact path | Required before |
|---|---|---|
| G0_CONTEXT | .gwc/tasks/<task-id>/g0/context-snapshot.yaml | Formal G0 exit |
| G1_ALIGNMENT | .gwc/tasks/<task-id>/g1/intake/g1-intake-brief.yaml, g1/preflight/g1-preflight-report.yaml, g1/brainstorming/g1-options.yaml, g1/decision/g1-decision-record.yaml | G1 exit |
| G2_EXECUTION | .gwc/tasks/<task-id>/g2/execution-envelope.yaml | Any guarded branch, worktree, or repository write |
| G3_PR | .gwc/tasks/<task-id>/g3/delivery-record.yaml | Draft PR creation or update |
| G4_MERGE | .gwc/tasks/<task-id>/g4/merge-approval.yaml | Merge or auto-merge action |
| G5_DEPLOY | .gwc/tasks/<task-id>/g5/deployment-approval.yaml | Manual deploy, release, publish, or runtime reload |
| G6_PRODUCTION_DATA | .gwc/tasks/<task-id>/g6/production-approval.yaml | Production data/configuration/credential/migration/secret action |

Every action packet that can cause a gate-scoped side effect must conform to
`schemas/gate-action-authority.schema.json` and pass
`tools/validate_gate_action.py`. The validator binds task, repository, base
SHA, head SHA, branch, gate, action, canonical scope hash, expiry, actor, and
readback event. A valid packet is evidence of a matching envelope; it is not a
new approval and never broadens the envelope's authorized actions.

The executable state transitions are defined in
`core/task-lifecycle/gate-transition-map.yaml`. G3 validation/review now ends
in `merge_pending`; G4 approval and merge move through `merge_running` to
`verification_running`; read-only G5 status verification ends in `completed`
only when no production operation is required. Manual deployment and
production operations use separate pending/running states and cannot be
inferred from a successful prior transition.

The G4, G5, and G6 rows are conditional. If a row is not applicable, the
current gate record must state not_applicable; absence is not permission.
Before invoking an action, the runtime must verify the applicable artifact's
presence, schema, freshness, and binding to the same task ID, repository, base
SHA, working branch, risk class, and scope hash. Failure is fail-closed with
GATE_ARTIFACT_MISSING, GATE_ARTIFACT_INVALID, or GATE_SCOPE_MISMATCH.

## Chat-only preparation

Exploratory G0/G1 conversation is not a formal gate exit. It may collect
context, brainstorm options, and refine a decision without physical artifacts,
task creation, or approval tokens. Label this state
`CHAT_ONLY_PREPARATION`; do not claim formal `READY` or `PASS`.

Formal G0/G1 evidence begins when the user requests transition to G2. At that
point the normal artifact, task-trace, validator, and G2 approval requirements
apply before any write-capable action.

## Gate definitions

### G0_CONTEXT

**Entry:** user request or assigned work item.

**Required evidence:** repository identity, protected base, active project profile, applicable governance sources, connector identity, and known blockers.

**Permitted actions:** read-only inspection.

**Exit:** `context-snapshot.yaml` is schema-valid with `status: READY` and no blockers.

### G1_ALIGNMENT

**Entry:** G0 is `READY`.

**Required evidence:** intake, preflight, options, explicit decision, non-goals, risks, constraints, and verifiable acceptance criteria.

**Permitted actions:** read-only analysis and decision capture.

**Exit:** `tools/validate_g01.py` returns `PASS`. Upon exit, the agent must proactively generate the G2 execution envelope and present the approval command to the user.

### G2_EXECUTION

**Entry:** G1 `PASS` plus a valid `execution-envelope.yaml` matching the same task, repository, base SHA, branch, and scope hash.

**Permitted actions:** only actions listed in `authorized_actions`, normally bounded branch writes and sandboxed validation.

**Prohibited actions:** protected-branch write, merge, deploy, release, production configuration, credentials, and production-data access.

**Exit:** implementation exists on the guarded branch; validation evidence and complete diff evidence are available. Upon exit, the agent must proactively generate the G3 delivery record and present the approval command to the user.

### G3_PR

**Entry:** G2 `PASS`, validation evidence exists, and complete diff review found no scope drift or prohibited changes.

**Permitted actions:** create or update a Draft Pull Request, assemble the canonical `g3/delivery-record.yaml`, and invoke or record an independent read-only review. G3 does not authorize the reviewer to modify the delivery.

G3 uses three internal stages without creating another gate:

```text
G3.1 PR Assembly
→ G3.2 Independent Review
→ G3.3 Review Closure
```

The review must:

- identify the implementer and reviewer;
- record `independent` only when the reviewer is separate from the implementer;
- record `fresh-context` when independence is approximated by a new context rather than a separate reviewer;
- evaluate the applicable requirement, design, code, test, governance, delivery, and CI lanes;
- bind evidence to the exact PR head SHA and scope hash;
- classify findings as `BLOCKER`, `MAJOR`, `MINOR`, or `NIT`;
- route blocking changes back to G2 for separately authorized revision;
- become stale after any PR head change and require re-review.

A reviewer that modifies the delivery loses reviewer independence. Another read-only review is then required for the new head SHA.

**Exit:** `delivery-record.yaml` is valid against `schemas/g3-delivery-record.schema.json`, identifies the Draft PR and exact head SHA, records validation and CI evidence, contains a non-stale review decision, maps acceptance criteria to evidence, records findings and residual risks, and preserves G4/G5/G6 exclusions. Upon exit, the agent may mark the Draft PR ready for review when a supported connector action exists, the latest head SHA is still current, required CI is green, no unresolved blocker exists, and no scope drift is detected. The agent must then proactively generate the G4 merge approval request and present the approval command to the user.

G3 may report `PASS` only when:

- the Draft PR and latest head SHA match the delivery record;
- the review covers the same head SHA and scope hash;
- every applicable review lane passes;
- no unresolved `BLOCKER` exists;
- every `MAJOR` is resolved or has explicit human risk acceptance for the exact head SHA;
- every acceptance criterion is passed or explicitly not applicable;
- required validation and CI checks pass for the exact head SHA;
- no material scope drift or prohibited change exists;
- residual risks and exclusions are recorded.

A schema-valid record with `outcome: fail` or `outcome: inconclusive` may retain unresolved findings so G3 can record `changes_required` or `blocked` and route the work back to G2. Validator `PASS` for such a record means the evidence is internally valid; it does not mean G3 passed.

Review `PASS` is G3 evidence only. It never grants merge authority; G4 still requires explicit human approval for the exact PR head SHA.

#### G3 asynchronous CI continuation

When CI is still running after Draft PR creation or after a repair push, G3 remains in validation monitoring rather than ending silently. The agent must record the current PR number, branch, latest head SHA, active work-tracking state, next check time, and continuation mechanism.

Continuation mechanisms are selected in this order:

1. webhook or CI event callback;
2. local sleep or poll loop for `local_agent` execution;
3. a two-minute sleep of the active thread for a ChatGPT chat connector;
4. a platform scheduler for another runtime when available;
5. manual checkpoint when no async mechanism is available.

For a ChatGPT chat connector, record repository, PR, expected head SHA, check-and-report-only authority, and the two-minute wake time before sleeping the current thread for exactly two minutes. It must not create a scheduler task or automation. The default next-check interval remains 3 minutes for every other continuation mechanism when supported by its active environment. Hosted non-ChatGPT schedulers that require a slower cadence must use the supported cadence and report that limitation.

If the ChatGPT chat connector cannot sleep and wake the current thread, it must use a manual checkpoint rather than create a scheduler task or automation. Other scheduled CI continuations remain inactive unless a concrete next run is visible or recorded.

If CI fails, the agent may diagnose and repair only repository-fixable failures within the active G2 scope. Any repair commit changes the latest head SHA and invalidates prior CI, review, and G4-readiness evidence. G4 approval may be generated only after required checks pass for the latest head SHA.

### G4_MERGE

**Entry:** G3 `PASS`, required CI checks pass, review requirements are satisfied, the Pull Request is ready for review, and explicit human approval is recorded for the exact PR head SHA.

**Permitted actions:** merge the approved PR using the authorized method.

**Draft PR precheck:** a Draft Pull Request is not eligible for G4 merge execution. Draft PR to ready-for-review transition belongs to G3 completion, not G4 authority. If the PR is still draft after G3 `PASS` and a ready-for-review connector is available, the agent may mark it ready before generating the G4 request. If no ready-for-review connector action exists, the agent must report a manual ready-for-review blocker.

**Exit:** merge commit or merged head evidence is recorded. Upon exit, the agent must automatically perform read-only `G5_STATUS_VERIFY` for the merge commit. A G5 approval command is required only for manual deploy, redeploy, release, publish, or runtime reload.

### G5_DEPLOY

**Entry:** G4 `PASS`. Read-only `G5_STATUS_VERIFY` starts automatically for the exact merge commit. Explicit human G5 approval is required only when the requested G5 action changes an environment or runtime.

**Default permitted actions:** verify post-merge GitHub Actions, deployment checks such as Vercel checks integrated into GitHub Actions, deployment status, and runtime/tool-surface status for the approved commit. These read-only checks do not require human approval.

**Post-merge verification procedure:** read-only `G5_STATUS_VERIFY` must bind evidence to the exact merge commit. The agent must first attempt exact post-merge lookup using `event=push`, `branch=main`, and `head_sha=<merge_sha>` or equivalent connector parameters. If the available connector surface does not support those filters, or returns empty results, the agent must fall back to a known `run_id` and direct jobs/artifacts lookup. Empty PR-filtered results without run-id/artifact fallback evidence must be classified `CONNECTOR_OBSERVABILITY_INCOMPLETE`, not `CI_PENDING`.

**Manual deploy actions:** manually deploying, redeploying, publishing, releasing, or reloading runtime is permitted only when that action is explicitly listed in the G5 approval scope and the active project profile requires or allows manual deployment. When deployment is already automated by CI/CD, G5 is status verification only.

**Exit:** status evidence is recorded, including checked workflow or deployment names, conclusions, environment when known, release or commit SHA, and rollback evidence when applicable. Upon exit, the agent must generate a G6 approval request only when a production-data, production-configuration, migration, credential, or secret operation is actually in scope. Otherwise G6 is recorded as `not_applicable` and no G6 command is generated.

### G6_PRODUCTION_DATA

**Entry:** explicit human approval for the precise production-data, production configuration, migration, credential, or secret operation, including expiry and scope.

**Permitted actions:** only the approved production operation.

**Exit:** operation result and audit evidence are recorded. Approval expires after the operation or its stated expiry time.

## Proactive Gate Transition

Every gate exit requires the agent to proactively generate the next needed artifact or action. Approval commands are required only at human-authority boundaries. Read-only `G5_STATUS_VERIFY` after G4 merge is automatic, and G6 is generated only when production data, production configuration, migration, credentials, or secrets are actually in scope. This ensures no gate ends in a silent state and the user always has a clear, actionable next step.
Read-only `G5_STATUS_VERIFY` starts automatically after G4 merge.

Compatibility note: legacy wording that the agent must present the corresponding approval command to the user applies only when the next step is a human-authority boundary. It does not apply to automatic read-only `G5_STATUS_VERIFY`.

The agent must:

1. Confirm the current gate's exit criteria are fully satisfied.
2. Generate the next gate's entry artifact (execution envelope, delivery record, or approval record) using the current gate's evidence.
3. Present the generated approval command in a standalone fenced text block.
4. Wait for the user to execute the command before proceeding to the next gate.
5. Update the active work-tracking task through its legal provider transition that corresponds to the gate transition before continuing. If the update fails, report the blocker or record a clearly labeled late reconciliation note; never backdate or invent task state evidence.

The user retains sole authority to grant or deny the next gate. The agent's proactive generation is a convenience mechanism, not a delegation of authority.

## Action-to-gate mapping

| Action | Minimum gate |
|---|---|
| Read repository or inspect CI | G0_CONTEXT |
| Create/update files on guarded branch | G2_EXECUTION |
| Push guarded branch | G2_EXECUTION |
| Create/update Draft PR | G3_PR |
| Mark Draft PR ready for review after G3 `PASS` | G3_PR |
| Merge PR | G4_MERGE |
| Verify post-merge CI, deployment checks, Vercel status, or runtime/tool surface | G5_DEPLOY, automatic when read-only |
| Manually deploy, redeploy, publish, release, or reload runtime | G5_DEPLOY with explicit manual action scope |
| Read/write production data, production config, migration, credential rotation, or secret operation | G6_PRODUCTION_DATA |

## Lane integrity and evidence readback

This section is normative for every governed agent before a repository write and
after a G4 approval. It exists to prevent lane drift, foreign working-tree
contamination, missing trusted receipts, and status claims bound to stale or
adjacent CI.

### Pre-write lane assertion

Before the first repository write of a session, and again after any change of
task, branch, worktree, or base SHA, the agent MUST emit a compact lane
assertion and MUST NOT write until it is emitted and self-consistent:

```text
LANE ASSERTION
task:        <task-id>
branch:      <working-branch>            # never a protected branch
worktree:    <absolute-checkout-path>
base_sha:    <exact-base-sha>
deliverable: <one-line scope of this lane>
```

Blocking conditions:

- the resolved branch is `main` or another protected branch -> the write is
  refused with `GATE_ACTION_NOT_AUTHORIZED`;
- the worktree path does not match the task lane -> `LANE_DRIFT_DETECTED`;
- the assertion is absent -> `LANE_ASSERTION_MISSING`.

### Foreign dirty state

Before staging, the agent MUST list the working-tree changes and classify every
path as either in-lane (produced by the current task) or FOREIGN DIRTY STATE
(pre-existing modifications belonging to another task family, another agent
run, or generated runtime output).

Rules:

1. report foreign paths explicitly under the label `FOREIGN DIRTY STATE`, with a
   count and representative paths;
2. never `git add -A`, `git add .`, or `git commit -a` when foreign dirty state
   exists;
3. stage only explicit in-lane paths;
4. do not revert, clean, or otherwise mutate foreign paths — preservation is the
   default; removal requires a separate authorized change;
5. when foreign paths cannot be classified with confidence, fail closed with
   `FOREIGN_DIRTY_STATE_DETECTED` and ask the operator.

### Post-approval readback

After an exact human G4 approval comment is posted, the chain is NOT healthy
until BOTH of the following are read back and reported:

1. the `issue_comment` workflow run triggered by that comment — exact run ID,
   status, and conclusion;
2. the trusted bot receipt comment `gwc:g4-authority-receipt` — posted by the
   trusted bot identity, bound to the same approval ID, approved head SHA, and
   scope hash.

If either is missing, the state is `G4_RECEIPT_MISSING` and merge must not be
treated as authorized on the strength of the human comment alone.

### Fail-closed recovery path

If a trusted G4 receipt is missing after merge, the agent MUST fail closed and
MUST NOT infer authority from adjacent evidence. It reports
`G4_RECEIPT_MISSING` and directs the operator to the bootstrap recovery
command rather than leaving diagnosis implicit:

```text
APPROVE G5 RECOVERY <recovery_id> <repo> <pr> <approval_id> <scope> <head> <merge> <validate_run> <build_run> <source_digest> <expires>
```

Any recovered evidence MUST bind:

- `<head>`: the exact approved head SHA (not the branch tip at read time);
- `<merge>`: the exact merge commit SHA;
- `<validate_run>` and `<build_run>`: run IDs of successful `push`-to-`main`
  runs whose `head_sha` equals `<merge>` exactly;
- `<source_digest>`: provenance binding for the recovered evidence payload;
- `<expires>`: an unexpired UTC timestamp at use time.

A recovery that cannot satisfy every binding is `RECOVERY_EVIDENCE_UNBOUND` and
must not be reported as recovered.

### Exact-binding status reporting

Final governed status for merge and recovery lanes MUST bind each claim to
exact SHAs and exact workflow run IDs. Prohibited: "CI is green", latest-run
lookups, branch-tip lookups, PR-filtered results without exact `head_sha`
match, and runs from adjacent or superseded commits. A status that cannot cite
the exact merge SHA and the exact run IDs is reported as
`CONNECTOR_OBSERVABILITY_INCOMPLETE` or `SHA_MISMATCH`, never as `success`.

## Failure codes

```text
LANE_ASSERTION_MISSING
LANE_DRIFT_DETECTED
FOREIGN_DIRTY_STATE_DETECTED
G4_RECEIPT_MISSING
RECOVERY_EVIDENCE_UNBOUND
GATE_ARTIFACT_MISSING
GATE_ARTIFACT_INVALID
GATE_SEQUENCE_INVALID
GATE_SCOPE_MISMATCH
GATE_ACTION_NOT_AUTHORIZED
GATE_APPROVAL_EXPIRED
GATE_HUMAN_APPROVAL_REQUIRED
GATE_EVIDENCE_MISSING
```

## Compatibility

This contract reuses the existing G0/G1 schemas and validator. G2-G6 use the generic gate evidence schema and action validator. Existing project profiles and approval-envelope semantics remain authoritative where they are stricter.
