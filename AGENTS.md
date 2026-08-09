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

## Agent-specific routing

The shared boot, execution modes, gate lifecycle, connector-call enforcement,
and authority boundaries in this file apply to every agent. Agent-specific
instructions add runtime behavior; they do not replace or duplicate this file.

## GWC ChatGPT response language

ChatGPT-style agents operating in GWC project chat must respond Vietnamese-first.
Keep English only where it preserves executable or technical precision, including gate names, exact approval commands, file paths, branch names, commit SHAs, tool names, code, YAML, JSON, and API identifiers.

A response that primarily explains governance, status, next action, blockers, or evidence should use Vietnamese as the main language.

- ChatGPT-style agents must also read
  `agents/chatgpt-agent/agent-instructions.md`.
- Other agents must read their applicable instructions and capability
  declaration under `agents/`.
- Select execution mode from verified capabilities, not agent product, name, or
  conversation surface. A ChatGPT-style agent with a trusted checkout, shell,
  filesystem, Git, isolated worktree support, and validator runner uses
  `local_agent`; without a trusted checkout it uses `chat_connector_only`, even
  when `/mnt`, a command runner, and GWC validator execution are available.
- Validator availability does not determine execution mode.
- Connector availability determines the verified connector route. It does not
  change execution mode when a trusted local checkout is already available.

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
   `ea3e44ac2d948b8439e9768bea4f5dda8474a34e914592130965083792a5ee48`.
4. Resolve exactly one active project profile.
5. Verify repository owner, repository name, default branch, protected branches,
   connector identity, `identity_status`, and `write_enabled`.
6. Resolve and report the execution mode, task ID, risk class, current gate,
   required next gate, authorized actions, and excluded actions.

The agent must not claim that G0 or G1 was completed merely because it inspected
or reasoned about the repository in conversation. Gate completion requires the
canonical repository artifacts and validator result appropriate to the current
execution mode.

Failure codes:

```text
POLICY_BOOT_FAILED
PROJECT_PROFILE_INVALID
INSTRUCTION_PACKAGE_INVALID
INSTRUCTION_DRIFT_DETECTED
EXECUTION_MODE_UNSUPPORTED
GATE_ARTIFACT_MISSING
GATE_ARTIFACT_INVALID
GATE_SEQUENCE_INVALID
GATE_SCOPE_MISMATCH
GATE_ACTION_NOT_AUTHORIZED
GATE_HUMAN_APPROVAL_REQUIRED
AI_AGENT_CLAIM_CONFLICT
```

## Conversational G0/G1 mode

When the user is exploring or brainstorming in chat-only mode, G0/G1 may be
performed as a conversation-local interaction. Do not require physical G0/G1
artifacts, work-item creation, or an approval token merely to discuss,
compare, or refine options. Label this state `CHAT_ONLY_PREPARATION`; it is not
formal G0/G1 completion.

When the user explicitly requests transition to G2, switch to formal mode:
create the task-scoped G0/G1 artifacts, create or claim the required task through
the active profile provider, validate them, and generate the exact G2 approval command before any
write-capable action.

## Run ID convention

Every G0/G1 session must declare a `run_id` before producing artifacts.

Formats:
- When a task ID is available: `g1-<task-id-short>-<YYYYMMDD-HHMM>`
- When no task ID: `g1-<YYYYMMDD-HHMM>-<short-kebab-topic>`

Rules:
- Maximum 64 characters. Alphanumeric and hyphens only.
- Same `run_id` for all G1 outputs in the same session.
- New `run_id` when task, repository, base SHA, selected option, or user decision changes materially.
- Do not reuse a `run_id` across independent sessions.

## Workspace location convention

Before producing G0 or G1 artifacts, the agent must select a workspace root according to this decision matrix:

| Mode | G0 location | G1 location | Validator command |
|---|---|---|---|
| `chat_connector_only` with `/mnt` | `/mnt/<session>/.gwc/tasks/<task-id>/g0/` | `/mnt/<session>/.gwc/tasks/<task-id>/g1/` | `--workspace /mnt/<session>/.gwc/tasks/<task-id>` |
| `chat_connector_only` without `/mnt` | `.gwc/tasks/<task-id>/g0/` | `.gwc/tasks/<task-id>/g1/` | `--workspace .gwc/tasks/<task-id>` |
| `local_agent` | `.gwc/tasks/<task-id>/g0/` | `.gwc/tasks/<task-id>/g1/` | `--workspace .gwc/tasks/<task-id>` |

Conflict policy:
- Do not allow two active sessions to write the same workspace root.
- Every new formal task MUST use `.gwc/tasks/<task-id>/` as its only artifact root; `run_id` is session metadata, not a root selector.
- `.gwc/g0`, `.gwc/g1`, and `.gwc/runs/<run_id>` are read-only compatibility layouts and MUST NOT be selected for new tasks.
- Never overwrite task-scoped artifacts unless the same task ID owns them or the user explicitly supersedes.

### Task-scoped gate artifacts

For formal work, every write-applicable gate artifact belongs under the same
task workspace. A gate action is blocked with GATE_ARTIFACT_MISSING,
GATE_ARTIFACT_INVALID, or GATE_SCOPE_MISMATCH when its artifact is absent,
invalid, stale, or bound to another task, repository, base SHA, working branch,
or scope hash.

| Gate | Required artifact | Applicability |
|---|---|---|
| G0_CONTEXT | .gwc/tasks/<task-id>/g0/context-snapshot.yaml | Always |
| G1_ALIGNMENT | .gwc/tasks/<task-id>/g1/{intake,preflight,brainstorming,decision}/*.yaml | Always |
| G2_EXECUTION | .gwc/tasks/<task-id>/g2/execution-envelope.yaml | Before any G2 write |
| G3_PR | .gwc/tasks/<task-id>/g3/delivery-record.yaml | Before Draft PR action |
| G4_MERGE | .gwc/tasks/<task-id>/g4/merge-approval.yaml | Only when merge is in scope |
| G5_DEPLOY | .gwc/tasks/<task-id>/g5/deployment-approval.yaml | Only for manual deploy/release/reload |
| G6_PRODUCTION_DATA | .gwc/tasks/<task-id>/g6/production-approval.yaml | Only for production data/config/credential/migration work |

When G4, G5, or G6 is not applicable, record not_applicable in the current
gate outcome and do not create a misleading approval artifact. The artifact
path, task ID, and gate applicability must be checked before the connector
action; a later gate never inherits an earlier gate's artifact.

## Execution modes

The agent must declare exactly one execution mode before gate reporting.

### `chat_connector_only`

Use this mode when the agent can read repositories and call connectors but has
no trusted local repository checkout. A missing trusted checkout does not imply
that `/mnt`, a command runner, or GWC validator execution is unavailable.

Allowed:

- read repository, task, PR, CI, and governance context;
- produce a conversation-local G0/G1 gate packet;
- materialize exact connector-fetched content into an isolated workspace when a
  writable filesystem is available;
- run protected-base validators against materialized task artifacts when a
  command runner is available;
- identify missing artifacts, validators, and blockers;
- draft a proposed patch plan or PR body;
- create repository changes through an authorized repository write connector
  when valid gate artifacts, validator evidence, scope, claim, and exact
  authority exist.

Not allowed:

- claim `G1_ALIGNMENT: PASS` without validator evidence;
- create a branch or mutate repository files merely from chat reasoning;
- backfill G0/G1 artifacts after connector writes.

If validator evidence is unavailable, first attempt exact-source recovery and
materialized validation when connector reads, writable isolated storage, and a
command runner are available. Only after that recovery is impossible may the
agent report validator unavailability.

### `local_agent`

Use this mode when the agent has a trusted local checkout, shell, filesystem,
Git, and isolated session/worktree capability.

Before repository mutation, the local agent must materialize task-scoped G0/G1
artifacts, run `tools/validate_g01.py`, and retain the validator evidence. Only
then may it enter G2, create the guarded branch/worktree, and perform scoped
repository writes.
If the current `main` checkout is dirty, stop using it and switch to a fresh
isolated worktree before any repository mutation.

### `repo_ci`

Use this mode inside GitHub Actions or another CI runner. CI validates committed
gate artifacts and repository policy after a branch or PR exists. CI is a second
boundary; CI success does not retroactively authorize pre-write actions and does
not grant merge, deployment, or production authority.

## Chat connector capability and route precedence

In `chat_connector_only`, resolve these capabilities independently rather than
collapsing them into the execution-mode label:

```text
repository_read_capability
local_materialization_capability
validator_execution_capability
repository_write_connector_capability
```

Connector content/text/blob plus writable isolated storage is sufficient for
materialization; a mounted connector file is not required. Missing one
capability blocks only actions that require that capability.

After trusted G0/G1 validation and exact applicable G2 authority, an authorized
GitHub/repository connector may create the guarded branch and perform scoped
repository writes. Local Git remains non-authoritative and is not required for
that connector action.

Generic gate wording defines the default authority path. Canonical
route-specific authority supplies the gate authority source when it validates
the exact action and bindings. For
`AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`, a trusted/current parent authority plus a
valid derived child G2 satisfies bounded `auto/*` child execution, and a valid
exact-head standing G4 satisfies the bounded `auto/* → pre-prod` child merge.
Do not request redundant Human G2/G4 for those exact authorized child actions.
The route-specific execution base is `pre-prod`, even though the repository
default branch is `main`. Human G4 remains mandatory for `pre-prod → main`.
Standing authority never authorizes merge to `main`.

## Mandatory gate sequence

The agent must follow this order without skipping or retroactively inventing
evidence:

```text
G0_CONTEXT
→ G1_ALIGNMENT
→ G2_EXECUTION
→ G3_PR
→ G4_MERGE
→ G5_DEPLOY (status check unless manual deploy is explicitly in scope)
→ G6_PRODUCTION_DATA (only when applicable)
```

### G0_CONTEXT — read only

Before entering G2, the agent must create, obtain, or cite the task-scoped G0 context
artifact and verify that it records:

- active project profile;
- repository identity and protected base SHA;
- connector identity;
- applicable governance sources and their hashes;
- task or work-item identity;
- blockers and risk signals.

Formal G0 is complete only when the artifact is schema-valid, has `status: READY`, and
contains no blockers. During G0 only read-only inspection is allowed.

### G1_ALIGNMENT — read only

Before entering G2, the agent must create, obtain, or cite the task-scoped G1 artifacts:

```text
g1-intake-brief.yaml
g1-preflight-report.yaml
g1-options.yaml
g1-decision-record.yaml
```

The agent must run or cite `tools/validate_g01.py` evidence against that task
workspace. G1 is complete only when the validator returns `PASS`.

A conversational agreement, a user request such as “apply fix”, or an agent's
own recommendation does not replace a G1 `PASS`.

**Proactive transition:** Upon G1 `PASS`, the agent must immediately generate
the G2 execution envelope and present the approval command to the user. The
agent must not wait for the user to ask for the next step. When canonical
route-specific trusted standing/derived authority already satisfies the exact
G2 action, resolve and use that authority instead of requesting a redundant
Human G2 token.

### G2_EXECUTION — guarded branch only

G2 requires:

- G0 `READY`;
- G1 validator `PASS`;
- a valid task-scoped execution/approval envelope or a canonical route-specific
  derived G2 authority decision;
- repository, base SHA, working branch, scope hash, risk, file/module scope, and
  authorized actions matching the intended connector call;
- a valid work-item claim when the profile requires one.

Only actions explicitly listed in the active envelope/authority are allowed. G2
never allows protected-branch writes, merge, deployment, release, credential
changes, production configuration, or production-data operations.

**Proactive transition:** Upon G2 exit, the agent must immediately generate the
G3 delivery record and present the approval command to the user when human
authority is required by the active route.

### G3_PR — Draft PR only

G3 requires completed G2 evidence, applicable validation, complete diff review,
no scope drift, and a delivery record for the exact head SHA. G3 may create or
update a Draft Pull Request only.

**Proactive transition:** Upon G3 `PASS`, resolve the active route's G4 authority
source. Generate a Human G4 request only when the route requires human authority
for that exact target/action. A valid standing G4 for bounded `auto/* → pre-prod`
is not replaced by a redundant human request.

### G4_MERGE, G5_DEPLOY, G6_PRODUCTION_DATA

These are separate authority gates. Human authority is the default; a canonical
route-specific policy may supply bounded standing authority for an exact action.
Authority for one gate never grants another gate. Human G4 remains mandatory for
merge/promotion to `main`.

G4 requires the Pull Request to be ready for review before the agent issues a
merge-ready G4 approval request or invokes a merge connector. A Draft PR is a
G4 blocker at merge time. After G3 `PASS`, the agent may automatically mark the
Draft PR ready for review when a connector action exists and the latest head SHA,
required CI, review closure, G3 evidence, and scope-drift checks are satisfied.
This ready-for-review transition is G3 metadata completion; it is not G4 approval
and never authorizes merge.

G5 is a status/deployment verification gate. Read-only `G5_STATUS_VERIFY` runs
automatically after G4 merge for the approved commit. It may check post-merge
workflow status, deployment check status, Vercel status, runtime status, or tool
surface. It does not authorize a manual deploy, redeploy, release, publish, or
runtime reload unless that manual action is explicitly in G5 manual-action scope.

For G5 evidence, the agent must first attempt exact post-merge lookup using
`event=push`, `branch=main`, and `head_sha=<merge_sha>` or equivalent connector
parameters. If the connector surface does not support those filters or returns
empty results, the agent must fall back to a known `run_id` and direct
jobs/artifacts lookup. Empty PR-filtered results without run-id/artifact fallback
evidence must be classified `CONNECTOR_OBSERVABILITY_INCOMPLETE`, not `CI_PENDING`.
`CI_PENDING` is reserved only when a post-merge run is found but has not yet
completed.

G6 is generated only when production data, production configuration, migration,
credential, or secret operations are actually in scope. Otherwise the agent
records `G6_PRODUCTION_DATA: not_applicable` and does not create a G6 approval
command.

**Proactive transition:** Upon G4 exit, the agent must automatically run
read-only `G5_STATUS_VERIFY` for the merge commit. The agent must request a G5
approval command only when a manual deploy, redeploy, release, publish, or
runtime reload is required. Upon G5 exit, the agent must generate a G6
production-operation request only when G6 scope exists. Each required command
must be presented to the user as a standalone approval command.

## Connector-call enforcement

Before invoking any write-capable tool or connector action, the agent must map
the action to its minimum gate and validate the current artifacts for the current
execution mode.

| Connector action | Minimum gate |
|---|---|
| Read/search/fetch repository or CI evidence | G0_CONTEXT |
| Create branch or worktree | G2_EXECUTION |
| Create, update, or delete repository files | G2_EXECUTION |
| Create commit, push branch, or update ref | G2_EXECUTION |
| Create or update Draft Pull Request | G3_PR |
| Mark Draft PR ready for review after G3 `PASS` | G3_PR |
| Merge or enable auto-merge | G4_MERGE |
| Verify post-merge CI, deployment checks, Vercel status, or runtime/tool surface | G5_DEPLOY, automatic when read-only |
| Manually deploy, redeploy, publish, release, or reload runtime | G5_DEPLOY with explicit manual action scope |
| Production data/config/migration/credential/secret operation | G6_PRODUCTION_DATA |

When required evidence is missing or invalid, the agent must stop before the
connector call and report the exact failure code. It must not proceed and later
backfill artifacts.

When a platform cannot technically execute the validator after exact-source
materialization/recovery attempts, the agent remains in verified read-only mode
unless trusted external validator evidence is already available. Tool
availability never grants authority; lack of a trusted checkout does not revoke
a separately available authorized repository write connector.

## Required user-visible gate reporting

For repository-changing work, the agent must visibly report gate transitions:

```text
GWC BOOT: PASS — execution_mode=<mode>
G0_CONTEXT: READY|BLOCKED — <evidence or blocker>
G1_ALIGNMENT: PASS|BLOCKED — <validator evidence or blocker>
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
