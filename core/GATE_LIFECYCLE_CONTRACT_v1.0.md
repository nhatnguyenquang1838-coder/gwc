# GWC Gate Lifecycle Contract v1.0

## Purpose

This contract defines the required entry evidence, permitted actions, exit evidence, and authority boundary for G0 through G6. It extends the existing G0/G1 artifact lifecycle without replacing it.

## Gate sequence

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ G4_MERGE
→ G5_DEPLOY
→ G6_PRODUCTION_DATA
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

**Exit:** `delivery-record.yaml` is valid against `schemas/g3-delivery-record.schema.json`, identifies the Draft PR and exact head SHA, records validation and CI evidence, contains a non-stale review decision, maps acceptance criteria to evidence, records findings and residual risks, and preserves G4/G5/G6 exclusions. Upon exit, the agent must proactively generate the G4 merge approval request and present the approval command to the user.

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

### G4_MERGE

**Entry:** G3 `PASS`, required CI checks pass, review requirements are satisfied, and explicit human approval is recorded for the exact PR head SHA.

**Permitted actions:** merge the approved PR using the authorized method.

**Exit:** merge commit or merged head evidence is recorded. Upon exit, the agent must proactively generate the G5 deployment approval request and present the approval command to the user.

### G5_DEPLOY

**Entry:** G4 `PASS` and explicit human deployment approval for the exact release or commit.

**Permitted actions:** deploy only the approved release to the approved environment.

**Exit:** deployment result, environment, release SHA, and rollback evidence are recorded. Upon exit, the agent must proactively generate the G6 production-data approval request and present the approval command to the user.

### G6_PRODUCTION_DATA

**Entry:** explicit human approval for the precise production-data, configuration, migration, or credential operation, including expiry and scope.

**Permitted actions:** only the approved production operation.

**Exit:** operation result and audit evidence are recorded. Approval expires after the operation or its stated expiry time.

## Proactive Gate Transition

Every gate exit requires the agent to proactively generate the entry artifact for the next gate and present the corresponding approval command to the user. This ensures no gate ends in a silent state and the user always has a clear, actionable next step.

The agent must:

1. Confirm the current gate's exit criteria are fully satisfied.
2. Generate the next gate's entry artifact (execution envelope, delivery record, or approval record) using the current gate's evidence.
3. Present the generated approval command in a standalone fenced text block.
4. Wait for the user to execute the command before proceeding to the next gate.

The user retains sole authority to grant or deny the next gate. The agent's proactive generation is a convenience mechanism, not a delegation of authority.

## Action-to-gate mapping

| Action | Minimum gate |
|---|---|
| Read repository or inspect CI | G0_CONTEXT |
| Create/update files on guarded branch | G2_EXECUTION |
| Push guarded branch | G2_EXECUTION |
| Create/update Draft PR | G3_PR |
| Merge PR | G4_MERGE |
| Deploy or publish release | G5_DEPLOY |
| Read/write production data, production config, migration, credential rotation | G6_PRODUCTION_DATA |

## Failure codes

```text
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