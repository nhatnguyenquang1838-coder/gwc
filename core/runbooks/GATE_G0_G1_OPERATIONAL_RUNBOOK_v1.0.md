# Gate G0/G1 Operational Runbook v1.0

## Purpose and scope

This is the canonical step-by-step operating procedure for G0_CONTEXT and G1_ALIGNMENT. It applies to all agents, all projects, and every supported execution mode. Project extensions may tighten this runbook but must not weaken it.

The runbook operationalizes, but does not replace, `core/Coding_Project_Governance_v1.0.md` and `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`.

## Core rule

A missing artifact, unavailable connector, transport error, or remediable evidence gap does not end the workflow. The agent must complete every permitted read-only or local preparation step, retry equivalent execution paths within the approved scope, and stop only at a real authority boundary or hard denial.

The agent must never report conversation-local reasoning as trusted `READY` or `PASS` evidence.

## Execution modes

### chat_connector_only

Use repository connectors for protected-base reads. When local filesystem and command execution are available, fetch the validator, schemas, and required sources into an isolated `/mnt` workspace, materialize task-scoped artifacts, and run the validator locally. Connector-only does not mean validator-unavailable when these capabilities exist.

### local_agent

Use an isolated checkout, session folder, or worktree. Materialize artifacts and run validators before repository mutation.

### repo_ci

Validate committed artifacts and policy in CI. CI is additional evidence and never retroactively grants authority.

## G0_CONTEXT procedure

1. Receive the request and identify the expected result.
2. Resolve exactly one active project profile.
3. Verify repository owner/name, default branch, protected branches, connector identity, and write-enabled status.
4. Read the canonical policy, active profile, active extension, root `AGENTS.md`, and applicable protected-base governance.
5. Resolve the exact protected-base commit SHA. When direct ref lookup fails, use an equivalent read-only method and verify equivalence before continuing.
6. Identify or create exactly one work item when the active profile requires DS Admin traceability. DS Admin records traceability only; it does not grant execution authority.
7. Classify risk and identify security, architecture, data, deployment, credential, destructive, and blast-radius signals.
8. Define initial scope, non-goals, expected files/modules, authorized actions, and excluded actions.
9. Classify blockers as:
   - self-remediable;
   - user-decision required;
   - external-write required;
   - missing capability;
   - hard denial.
10. Automatically resolve self-remediable blockers and retry equivalent connector paths that remain within the approved repository, base, branch, action, and scope.
11. Produce a structured G0 proposal for the user when trusted completion is not yet possible. Do not merely report `BLOCKED` and stop.
12. Create `g0/context-snapshot.yaml` in the task workspace.
13. Validate its schema and consistency.
14. Exit with exactly one truthful status:
   - `READY`: artifact valid, base resolved, no blockers;
   - `PROPOSED`: bounded proposal prepared for user decision;
   - `NOT_READY`: trusted persistence or validation still missing;
   - `DENIED`: hard prohibition or irreconcilable mismatch.

## Mandatory G0 proposal behavior

When a bounded safe proposal can be formed, the user-visible proposal must include task ID, objective, repository, protected base and SHA status, connector route, risk, candidate scope, authorized actions, exclusions, blockers, validation plan, scope-change triggers, next gate, and the exact approval command when applicable.

Missing write authority blocks only the external write. It does not block proposal preparation, local artifact generation, local validation, or other permitted read-only work.

## G1_ALIGNMENT procedure

1. Confirm G0 is `READY`, or explicitly label G1 work as conversation-local preparation when G0 trusted evidence is incomplete.
2. Create `g1/intake/g1-intake-brief.yaml` with problem statement, scope, non-goals, stakeholders, constraints, and verifiable acceptance criteria.
3. Create `g1/preflight/g1-preflight-report.yaml` with repository/profile consistency, risk analysis, dependency checks, capability checks, and blockers.
4. Create `g1/brainstorming/g1-options.yaml` with considered options, trade-offs, rejected alternatives, and selected direction.
5. Create `g1/decision/g1-decision-record.yaml` with the accepted decision, rationale, final scope, validation plan, rollback considerations, and explicit user decision.
6. Verify all four artifacts use the same project, repository, task trace, protected base, and scope.
7. Detect scope drift. Any material change to repository, base SHA, files, behavior, architecture, data/security impact, risk, or authorized actions requires a scope delta and new approval envelope.
8. Fetch `tools/validate_g01.py` and the referenced schemas from the protected base when no checkout exists.
9. Materialize an isolated workspace, preferably `/mnt/<session>/.gwc/tasks/<task-id>/` for connector sessions.
10. Run:

```bash
python tools/validate_g01.py --workspace .gwc/tasks/<task-id> --json
```

Use validator-specific root arguments when required by the checked-in tool.

11. Interpret results truthfully:
   - exit `0`: `PASS`;
   - exit `1`: artifacts present but invalid, inconsistent, or blocked;
   - exit `2`: configuration or I/O error.
12. Resolve remediable validation issues and rerun. Do not stop after the first correctable failure.
13. Preserve validator stdout, exit code, artifact hashes, and workspace path as evidence.
14. Enter G2 only after G0 `READY`, G1 `PASS`, a valid task-scoped execution envelope, and all mandatory checks pass.

## DS Admin traceability

When required by the active profile:

1. Search for a matching task using source reference or idempotency key.
2. Reuse exactly one matching task; do not create duplicates.
3. If none exists and task creation is authorized, create one with repository, base branch, objective, risk, scope, exclusions, and idempotency key.
4. Record the task ID in G0/G1 trace fields.
5. Fetch the authoritative DS MCP state contract through `task_state_contract_get`.
6. Resolve the gate outcome in `core/task-lifecycle/gate-transition-map.yaml`.
7. Verify the current state, transition, and expected destination are legal in the live contract.
8. Execute the transition with an idempotency key.
9. Read back the task and verify the observed state equals the expected state.
10. Record task ID, prior state, transition, expected state, observed state, and event/idempotency evidence.
11. Treat a missing, illegal, failed, or unverifiable transition as a failed gate DoD; do not report the gate complete.
12. Record branch, PR, validation outcome, and final state as they become available.
13. Never treat task creation, assignment, or state as approval for repository writes, merge, deployment, credentials, or production data.

## Connector failure and retry rules

For transport errors, unsupported parameter forms, timeouts, and capability mismatches, the agent must automatically try an equivalent route when all of the following remain unchanged:

- repository;
- protected base and verified SHA;
- working branch;
- requested action;
- risk and file scope;
- approval authority.

Examples include verifying `main` still equals the locked SHA before retrying branch creation from `main`, or using an approved API connector after the preferred GitHub connector is unavailable or lacks the capability.

Do not use fallback after governance denial, missing approval, protected-branch denial, scope mismatch, stale base SHA, or credential failure. API fallback is a transport fallback, never a governance fallback.

## Mandatory post-gate transition DoD

A gate that produces a lifecycle outcome is complete only when all of the following are true:

- gate artifacts and validation evidence are complete;
- the mapped transition exists in `core/task-lifecycle/gate-transition-map.yaml`;
- the live DS MCP contract permits the transition from the observed current state;
- the transition call succeeds idempotently;
- task read-back equals the mapped expected state;
- transition evidence is included in the gate report.

Failure to transition is not a reporting-only warning. It fails the gate and requires repair or an explicit blocked state.

## Transition to later gates

- G2 permits only the authorized guarded-branch execution scope.
- G3 permits Draft PR creation only after validation and complete diff review.
- G4 merge is separate HITL authority.
- G5 deployment/release is separate HITL authority.
- G6 production data/configuration/credentials/migration is separate authority.

No G0/G1 result grants G4, G5, or G6.

## Rescue and hotfix interaction

Rescue or hotfix may accelerate only the steps explicitly allowed by the canonical emergency contract. They never permit protected-branch writes, merge, deployment, credentials, production configuration, or production-data operations without their separate authority. When the emergency contract requires the standard path because an existing task or envelope exists, the agent must resume the standard path rather than attempt to bypass it.

## Required user-visible reporting

```text
GWC BOOT: PASS — execution_mode=<mode>
G0_CONTEXT: READY|PROPOSED|NOT_READY|DENIED — <evidence or blocker>
G1_ALIGNMENT: PASS|BLOCKED|FAILED|NOT_RUN — <validator evidence>
G2_EXECUTION: ENTERED|PASS|DENIED — <authorized actions or blocker>
G3_PR: ENTERED|PASS — <Draft PR and head SHA>
```

Keep reports concise. Continue automatically across remediable blockers and connector retries. Do not ask the user to repeat an already supplied decision or approval.

## Acceptance tests

1. Incomplete G0 evidence causes the agent to continue permitted inspection and produce a G0 proposal instead of stopping.
2. Connector-only mode with Git fetch, `/mnt`, and command execution materializes artifacts and runs the local validator.
3. A connector parameter error triggers an equivalent safe retry without a new approval when scope and authority are unchanged.
4. User acknowledgement of G0 permits G1 planning but does not grant repository-write authority.
5. `NOT_RUN` is never reported as `PASS`.
6. DS Admin task creation never replaces approval.
7. Governance denial, stale SHA, scope mismatch, and protected-branch denial fail closed without API fallback.
8. G3 creates Draft PR only and stops before G4.
9. G4, G5, and G6 remain separate HITL/authority gates.
