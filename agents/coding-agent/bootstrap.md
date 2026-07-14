# Coding Agent Bootstrap

At the start of every coding, repository, Pull Request, deployment, release,
configuration, migration, credential, or production-data task, the agent must
enter the GWC lifecycle before taking action.

## Mandatory read order

1. Read the protected-base `AGENTS.md`.
2. Read and verify:
   - `core/Coding_Project_Governance_v1.0.md`;
   - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`;
   - the active Project Profile;
   - project instructions and extension;
   - applicable agent instructions and capabilities;
   - the target repository's protected-base governance, package files, task,
     spec, and relevant workflows.
3. Locate the project package manifest and verify every package file hash.
4. Verify exactly one profile is active.
5. Verify repository owner, name, default branch, protected branches, connector,
   identity, and `write_enabled`.
6. Report:
   - policy version and SHA;
   - active profile;
   - repository and protected base SHA;
   - task ID;
   - risk class;
   - current and required gate;
   - authorized actions;
   - excluded actions.

Stop with `INSTRUCTION_PACKAGE_INVALID`, `POLICY_BOOT_FAILED`, or
`PROJECT_PROFILE_INVALID` when any required instruction, hash, profile, or
repository identity is missing, altered, conflicting, or unverified.

## Mandatory lifecycle

The agent must not create a branch, worktree, commit, repository file change,
push, or Pull Request until:

```text
G0_CONTEXT artifact = READY
G1 artifacts = complete
python tools/validate_g01.py --workspace <task-workspace> = PASS
G2 execution envelope = valid for the intended action
```

The agent must not treat repository inspection, conversation reasoning, a user
request, or an internal plan as a substitute for these artifacts.

Before every write-capable connector call, validate that the action is permitted
by the current gate and exact envelope scope. Missing or invalid evidence causes
a fail-closed stop with the relevant `GATE_*` failure code. Do not invoke the
action and backfill evidence afterward.

Draft Pull Request creation requires G3 evidence. Merge, deployment, release,
production configuration, migration, credential, and production-data operations
require separate G4, G5, or G6 human authority as defined by the lifecycle
contract.

When `claim_required_for_e2e` is true, do not create the G2 envelope, branch, or
modify the repository until the approved work item is successfully claimed and
ownership and lease are verified.

Do not retrieve or execute a newer instruction package automatically.
Instruction updates arrive only through an approved Git Pull Request.
