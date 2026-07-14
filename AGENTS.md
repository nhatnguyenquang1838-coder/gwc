# AGENTS.md — Instruction Governance Repository

This file governs every agent operating in this repository.

## Authority order

1. System, platform, developer, and active project runtime instructions
2. `core/Coding_Project_Governance_v1.0.md`
3. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
4. Active `projects/<project-id>/project-profile.yaml`
5. `projects/<project-id>/project-extension.md`
6. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
7. Agent-specific instructions under `agents/`
8. User request, provided it does not weaken higher authority

## Mandatory GWC boot

This boot is mandatory for every coding, repository, Pull Request, deployment,
release, configuration, migration, credential, or production-data task.

Before any write-capable connector action, the agent must:

1. Read this file from the protected base.
2. Read and verify:
   - `core/Coding_Project_Governance_v1.0.md`;
   - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`;
   - the active `projects/<project-id>/project-profile.yaml`;
   - the active project instructions and extension;
   - the applicable agent instructions and capability declaration;
   - the target repository's protected-base `AGENTS.md`, package files, task,
     spec, and workflow files relevant to the request.
3. Verify core version `1.0` and SHA-256
   `04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1`.
4. Resolve exactly one active project profile.
5. Verify repository owner, repository name, default branch, protected branches,
   connector identity, `identity_status`, and `write_enabled`.
6. State the task ID, risk class, current gate, required next gate, authorized
   actions, and excluded actions.

The agent must not claim that G0 or G1 was completed merely because it inspected
or reasoned about the repository in conversation. Gate completion requires the
canonical repository artifacts and validator result defined below.

Failure codes:

```text
POLICY_BOOT_FAILED
PROJECT_PROFILE_INVALID
INSTRUCTION_PACKAGE_INVALID
INSTRUCTION_DRIFT_DETECTED
GATE_ARTIFACT_MISSING
GATE_ARTIFACT_INVALID
GATE_SEQUENCE_INVALID
GATE_SCOPE_MISMATCH
GATE_ACTION_NOT_AUTHORIZED
GATE_HUMAN_APPROVAL_REQUIRED
```

## Mandatory gate sequence

The agent must follow this order without skipping or retroactively inventing
evidence:

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ G4_MERGE
→ G5_DEPLOY
→ G6_PRODUCTION_DATA
```

### G0_CONTEXT — read only

Before branch creation or repository modification, the agent must create or
update the task-scoped G0 context artifact and verify that it records:

- active project profile;
- repository identity and protected base SHA;
- connector identity;
- applicable governance sources and their hashes;
- task or work-item identity;
- blockers and risk signals.

G0 is complete only when the artifact is schema-valid, has `status: READY`, and
contains no blockers. During G0 only read-only inspection is allowed.

### G1_ALIGNMENT — read only

Before branch creation or repository modification, the agent must create or
update the task-scoped G1 artifacts:

```text
g1-intake-brief.yaml
g1-preflight-report.yaml
g1-options.yaml
g1-decision-record.yaml
```

The agent must run `tools/validate_g01.py` against that task workspace. G1 is
complete only when the validator returns `PASS`.

A conversational agreement, a user request such as “apply fix”, or an Agent's
own recommendation does not replace a G1 `PASS`.

### G2_EXECUTION — guarded branch only

G2 requires:

- G0 `READY`;
- G1 validator `PASS`;
- a valid task-scoped execution/approval envelope;
- repository, base SHA, working branch, scope hash, risk, file/module scope, and
  authorized actions matching the intended connector call;
- a valid work-item claim when the profile requires one.

Only actions explicitly listed in the active envelope are allowed. G2 never
allows protected-branch writes, merge, deployment, release, credential changes,
production configuration, or production-data operations.

### G3_PR — Draft PR only

G3 requires completed G2 evidence, applicable validation, complete diff review,
no scope drift, and a delivery record for the exact head SHA. G3 may create or
update a Draft Pull Request only.

### G4_MERGE, G5_DEPLOY, G6_PRODUCTION_DATA

These are separate human-authority gates. Approval for one gate never grants
another gate. Approval must match the exact repository, task, PR or release,
head SHA, scope hash, action, environment, and expiry where applicable.

## Connector-call enforcement

Before invoking any write-capable tool or connector action, the agent must map
the action to its minimum gate and validate the current artifacts.

| Connector action | Minimum gate |
|---|---|
| Read/search/fetch repository or CI evidence | G0_CONTEXT |
| Create branch or worktree | G2_EXECUTION |
| Create, update, or delete repository files | G2_EXECUTION |
| Create commit, push branch, or update ref | G2_EXECUTION |
| Create or update Draft Pull Request | G3_PR |
| Merge or enable auto-merge | G4_MERGE |
| Deploy or publish release | G5_DEPLOY |
| Production data/config/migration/credential operation | G6_PRODUCTION_DATA |

When required evidence is missing or invalid, the agent must stop before the
connector call and report the exact failure code. It must not proceed and later
backfill artifacts.

When a platform cannot technically execute the validator, the agent remains in
verified read-only mode. Tool availability never grants authority.

## Required user-visible gate reporting

For repository-changing work, the agent must visibly report gate transitions:

```text
GWC BOOT: PASS
G0_CONTEXT: READY
G1_ALIGNMENT: PASS
G2_EXECUTION: ENTERED — <authorized actions>
G2_EXECUTION: PASS — <validation evidence>
G3_PR: ENTERED
G3_PR: PASS — <Draft PR and head SHA>
```

Do not report a gate as `PASS` without repository evidence. Do not expose hidden
reasoning; report only the gate status, evidence, decisions, and blockers.

## Instruction source of truth

- Instruction source files live in this repository.
- Generated project packages are derived artifacts.
- Project repositories consume pinned packages.
- Do not edit generated rollout files and then back-port by hand.
- Every source instruction has an ID, version, lifecycle, scope, and owning
  package.

## CRUD rules

### Create

- Add the instruction source.
- Add or update package references.
- Add validation coverage.
- Record the change in `releases/changelog.md`.

### Read

- Read-only operations may inspect catalog, packages, manifests, history, and
  target rollout state.
- Do not claim write approval from a read-only inspection.

### Update

- Produce a semantic diff.
- Identify all consuming projects.
- Increment package version appropriately.
- Include rollout and rollback plans.

### Delete

Physical deletion is prohibited by default.

Use:

```text
active -> deprecated -> disabled -> archived
```

Physical deletion requires proof that no package or release references the
instruction and that historical releases remain reconstructable.

## Git write rules

- Never write directly to a protected branch.
- Use a dedicated branch and isolated worktree/session.
- Verify expected base and head SHA before every write.
- Do not force-push, rewrite shared history, delete branches, or change PR base.
- Open a Draft PR unless a stricter rule requires otherwise.

### DWC runtime on the GWC repository

When the verified `DWC` runtime operates on
`nhatnguyenquang1838-coder/gwc` under the active `gwc` profile:

- G0 inspection may be automatic, but G0 is not complete until its artifact is
  written and validated.
- G1 analysis may be automatic, but G1 is not complete until all G1 artifacts
  exist and `tools/validate_g01.py` returns `PASS`.
- G2 execution is automatic only for bounded non-risk work represented by one
  valid task and one valid execution envelope.
- G3 Draft PR creation is automatic only after G2 validation and delivery
  evidence exist.
- Repository writes are task-bounded rather than restricted to a fixed path
  allowlist.
- Explicit human direction is required for financial impact, architecture
  change, security-boundary change, production configuration, credentials or
  secrets, production data, destructive or irreversible change, or broad
  blast radius.
- An explicit user request may provide human direction for the stated bounded
  scope, but does not replace G0/G1 artifacts or grant G4, G5, or G6 authority.

The DWC runtime contract is defined in
`agents/dwc/agent-instructions.md`. Other agents continue to follow the
canonical approval protocol unless higher-priority runtime instructions state
otherwise.

## DS Admin task rules

For profiles where `work_tracking.claim_required_for_e2e` is true:

```text
No valid task claim
-> no G2 envelope
-> no branch
-> no worktree
-> no repository modification
-> no commit
-> no push
-> no Pull Request
```

Use State Engine operations only. Never invent task status or bypass claims,
leases, ownership, or legal transitions.

## Exact user command presentation

Every approval, activation, retry, or exact command requested from the user
must be placed in a standalone fenced text block. Put one command in each
block. Do not place placeholders in a command represented as executable.

## Validation

Before a Draft PR:

- validate all YAML and JSON;
- validate schemas;
- verify checksums and package references;
- validate G0/G1 and the requested gate action;
- inspect scripts before execution;
- run applicable tests;
- review the complete diff;
- detect secrets, accidental deletion, generated noise, and scope drift.

## Hard exclusions without separate authority

- merge or auto-merge;
- deployment or release;
- production configuration;
- credential rotation;
- production migration;
- production-data reads or writes;
- protected-branch direct push;
- force-push;
- branch deletion;
- shared-history rewrite;
- PR base change.

CI success is evidence only. It never grants authority.
