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

**Exit:** `tools/validate_g01.py` returns `PASS`.

### G2_EXECUTION

**Entry:** G1 `PASS` plus a valid `execution-envelope.yaml` matching the same task, repository, base SHA, branch, and scope hash.

**Permitted actions:** only actions listed in `authorized_actions`, normally bounded branch writes and sandboxed validation.

**Prohibited actions:** protected-branch write, merge, deploy, release, production configuration, credentials, and production-data access.

**Exit:** implementation exists on the guarded branch; validation evidence and complete diff evidence are available.

### G3_PR

**Entry:** G2 `PASS`, validation evidence exists, and complete diff review found no scope drift or prohibited changes.

**Permitted actions:** create or update a Draft Pull Request only.

**Exit:** `delivery-record.yaml` identifies the PR, head SHA, validation evidence, residual risks, and exclusions.

### G4_MERGE

**Entry:** G3 `PASS`, required CI checks pass, review requirements are satisfied, and explicit human approval is recorded for the exact PR head SHA.

**Permitted actions:** merge the approved PR using the authorized method.

**Exit:** merge commit or merged head evidence is recorded.

### G5_DEPLOY

**Entry:** G4 `PASS` and explicit human deployment approval for the exact release or commit.

**Permitted actions:** deploy only the approved release to the approved environment.

**Exit:** deployment result, environment, release SHA, and rollback evidence are recorded.

### G6_PRODUCTION_DATA

**Entry:** explicit human approval for the precise production-data, configuration, migration, or credential operation, including expiry and scope.

**Permitted actions:** only the approved production operation.

**Exit:** operation result and audit evidence are recorded. Approval expires after the operation or its stated expiry time.

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
