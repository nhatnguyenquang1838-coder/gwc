
# AGENTS.md — Instruction Governance Repository

This file governs every agent operating in this repository.

## Authority order

1. System, platform, developer, and active project runtime instructions
2. `core/Coding_Project_Governance_v1.0.md`
3. Active `projects/<project-id>/project-profile.yaml`
4. `projects/<project-id>/project-extension.md`
5. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
6. Agent-specific instructions under `agents/`
7. User request, provided it does not weaken higher authority

## Mandatory boot for coding, repository, PR, deployment, configuration,
migration, or production-data work

1. Read all four required policy files.
2. Verify core version `1.0`.
3. Verify core SHA-256:
   `04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1`.
4. Resolve exactly one project profile.
5. Verify repository identity, protected branches, connector, and
   `write_enabled`.
6. State the risk class, required gate, authorized actions, and exclusions.

Failure codes:

```text
POLICY_BOOT_FAILED
PROJECT_PROFILE_INVALID
INSTRUCTION_PACKAGE_INVALID
INSTRUCTION_DRIFT_DETECTED
```

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

- G0 intake and G1 read-only repository inspection are automatic.
- G2 execution is automatic for bounded non-risk work represented by one DS
  Admin task.
- G3 Draft PR creation is automatic after validation for bounded non-risk work.
- Repository writes are task-bounded rather than restricted to a fixed path
  allowlist.
- Explicit human direction is required for financial impact, architecture
  change, security-boundary change, production configuration, credentials or
  secrets, production data, destructive or irreversible change, or broad
  blast radius.
- An explicit user request to create the bounded PR grants branch,
  implementation, validation, push, and Draft PR authority for that scope only.

The DWC runtime contract is defined in
`agents/dwc/agent-instructions.md`. Other agents continue to follow the
canonical approval protocol unless higher-priority runtime instructions state
otherwise.

## DS Admin task rules

For profiles where `work_tracking.claim_required_for_e2e` is true:

```text
No valid task claim
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
