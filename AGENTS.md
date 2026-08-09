# AGENTS.md — Instruction Governance Repository

This file governs every agent operating in this repository.

## Authority order

1. System, platform, developer, and active project runtime instructions
2. `core/Coding_Project_Governance_v1.0.md`
3. `core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md` when the active canonical route is `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`; otherwise not applicable
4. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
5. Active `projects/<project-id>/project-profile.yaml`
6. `projects/<project-id>/project-extension.md`
7. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
8. Agent-specific instructions under `agents/`
9. User request, provided it does not weaken higher authority

### Route resolution precedes generic workflow rules

`ROUTE_RESOLUTION_PRECEDES_GENERIC_WORKFLOW` is a repository invariant.

Before applying generic gate, project-extension, E2E, runbook, or agent wording
about which actor must authorize an action, the agent MUST resolve the active
canonical route and its authority source. Route-specific authority does not
bypass the gate; it supplies the authority source for that exact gate/action.

For `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`:

- the canonical autonomous policy is authoritative for bounded child G2/G4
  authority and is evaluated before generic Human-G2/Human-G4 defaults;
- a trusted/current parent authority plus valid derived child G2 satisfies the
  exact allowlisted `auto/*` child execution scope;
- a valid exact-head standing G4 satisfies only the bounded
  `auto/* -> pre-prod` merge it binds;
- E2E supplies delivery mechanics and MUST NOT replace a valid standing G4 with
  a redundant Human G4 request or force a Draft-PR STOP when the canonical route
  separately authorizes continuation;
- a missing, stale, drifted, or invalid autonomous authority fails closed under
  the autonomous policy and MUST NOT be silently repaired by switching the same
  child action to generic Human G4 semantics;
- Human G4 remains mandatory for every `pre-prod -> main` promotion/merge;
- autonomous standing authority never authorizes merge to `main`.

Any lower-priority statement that says G4 is "always human" or that E2E "never
merges" is a generic default and MUST be interpreted under this route-precedence
rule when a canonical route is active.

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
release, configuration, migration, credential, or production-data task unless a
higher-priority runtime/user instruction explicitly disables GWC for the current
operation.

Before any write-capable connector action under GWC, the agent must:

1. Read this file from the protected base.
2. Read and verify:
   - `core/Coding_Project_Governance_v1.0.md`;
   - `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
   - `core/E2E_DRAFT_PR_DELIVERY_RULE.md`;
   - `core/AUTONOMOUS_PREPROD_INTEGRATION_POLICY_v1.0.md` whenever autonomous route metadata, parent-run authority, or `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN` is in scope;
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
6. Resolve the active route before applying generic workflow authority defaults,
   then report the execution mode, task ID, risk class, current gate, required
   next gate, authority source, authorized actions, and excluded actions.

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
write-capable action, unless the active canonical route supplies an already
valid derived/standing G2 authority for that exact action.

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
| G4_MERGE | .gwc/tasks/<task-id>/g4/merge-approval.yaml or canonical route-specific G4 authority evidence | Only when merge is in scope |
| G5_DEPLOY | .gwc/tasks/<task-id>/g5/deployment-approval.yaml | Only for manual deploy/release/reload |
| G6_PRODUCTION_DATA | .gwc/tasks/<task-id>/g6/production-approval.yaml | Only for production data/config/credential/migration work |

When G4, G5, or G6 is not applicable, record not_applicable in the current
gate outcome and do not create a misleading approval artifact. When a canonical
route defines a different G4 authority evidence type, validate that exact route
evidence instead of fabricating a generic Human approval artifact. The artifact
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

The agent MUST resolve the canonical route before applying generic workflow
authority defaults. Generic gate wording defines the default authority path;
canonical route-specific authority supplies the gate authority source when it
validates the exact action and bindings. E2E mechanics do not define or replace
the route-specific authority source.

For `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`, a trusted/current parent authority
plus a valid derived child G2 satisfies bounded `auto/*` child execution, and a
valid exact-head standing G4 satisfies the bounded `auto/* -> pre-prod` child
merge. Do not request redundant Human G2/G4 for those exact authorized child
actions. The route-specific execution base is `pre-prod`, even though the
repository default branch is `main`. Human G4 remains mandatory for
`pre-prod -> main`. Standing authority never authorizes merge to `main`.

If autonomous authority is missing or invalid, fail closed with the applicable
autonomous reason code. Do not reinterpret the same autonomous child merge as a
generic Human-G4 route merely to make it executable.

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
for that exact target/action. A valid standing G4 for bounded `auto/* -> pre-prod`
is not replaced by a redundant human request.

### G4_MERGE, G5_DEPLOY, G6_PRODUCTION_DATA

These are separate authority gates. Human authority is the default; a canonical
route-specific policy may supply bounded standing authority for an exact action.
Authority for one gate never grants another gate. Human G4 remains mandatory for
merge/promotion to `main`.

G4 requires the Pull Request to be ready for review before the agent issues a
merge-ready Human G4 approval request or invokes a merge connector under the
resolved route-specific G4 authority. A Draft PR is a G4 blocker at merge time.
After G3 `PASS`, the agent may automatically mark the Draft PR ready for review
when a connector action exists and the latest head SHA, required CI, review
closure, G3 evidence, and scope-drift checks are satisfied. This ready-for-review
transition is G3 metadata completion; it is not G4 approval and never authorizes
merge.

G5 is a status/deployment verification gate. Read-only `G5_STATUS_VERIFY` runs
automatically after G4 merge for the approved commit. It may check post-merge
workflow status, deployment check status, Vercel status, runtime status, or tool
surface. It does not authorize a manual deploy, redeploy, release, publish, or
runtime reload unless that manual action is explicitly in G5 manual-action scope.

For G5 evidence, the agent must first attempt exact post-merge lookup using the
actual merge target branch and `head_sha=<merge_sha>` or equivalent connector
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
| Merge or enable auto-merge | G4_MERGE with the authority source selected by the active canonical route |
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

Use:

```text
active -> deprecated -> disabled -> archived
```

Physical deletion requires proof that no package or release references the
instruction and that historical releases remain reconstructable.

## Git write rules

- Never write directly to a protected branch during normal governed execution.
- Use a dedicated branch and isolated worktree/session.
- Verify expected base and head SHA before every write.
- Do not force-push, rewrite shared history, delete branches, or change PR base.
- Open a Draft PR unless a stricter rule requires otherwise.

These normal governed Git rules do not redefine the authority source for a
separately validated route-specific G4 merge. A canonical standing G4 may
authorize the exact PR merge it binds; it does not authorize a direct protected-
branch push.

### DWC runtime on the GWC repository

When the verified `DWC` runtime operates on
`nhatnguyenquang1838-coder/gwc` under the active `gwc` profile:

- G0 inspection may be automatic, but G0 is not complete until its artifact is
  written and validated, or trusted validator evidence is cited.
- G1 analysis may be automatic, but G1 is not complete until all G1 artifacts
  exist and `tools/validate_g01.py` returns `PASS`.
- In `chat_connector_only` mode, DWC must remain read-only unless trusted G0/G1
  validator evidence and a valid envelope already exist.
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
  scope, but does not replace G0/G1 artifacts or itself grant G4, G5, or G6
  authority. Canonical route-specific standing authority is resolved separately.

The DWC runtime contract is defined in
`agents/dwc/agent-instructions.md`. Other agents continue to follow the
canonical approval protocol unless higher-priority runtime instructions state
otherwise.

## Work-tracking task rules

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

Use active-provider operations only. Never invent task status or bypass claims,
leases, ownership, or legal transitions.

The agent must synchronize the active work-tracking provider before continuing
across gate boundaries. Use only legal provider transitions. If task state falls
behind repository work, perform a clearly labeled late reconciliation and disclose
the limitation; never backdate, fabricate, or claim earlier task state.

Recommended mapping:

| Gate moment | Work-tracking transition target |
|---|---|
| G0/G1 analysis starts | `agent_running` |
| G0/G1 proposal is ready | `pending_review` |
| User selects the plan | `pending_approval` |
| G2 write starts | `write_running` |
| PR is created | `validation_running` |
| CI and validation pass | `completed` |
| Blocker found | `blocked` |
| Irrecoverable failure | `failed` |

## AI agent task claim (multi-agent ownership)

The task provider for `gwc` is `jira-mcp`. Multiple AI agents (ChatGPT, Kilo,
OpenClaw, Hermes, Codex) may claim Jira tasks through their own Jira MCP. The
claim records *which* agent logically owns the task; it does not create Jira user
accounts for the agents.

When an agent claims a task, it must set two custom fields in addition to the
existing work-tracking transition:

| Field | Jira type | Jira ID (SCRUM) | Purpose |
|---|---|---|---|
| `AI Agent` (text) | free text | `customfield_10046` | which AI agent owns the task (one of `ChatGPT`, `Kilo`, `OpenClaw`, `Hermes`, `Codex`) |
| `Claimed At` (datetime) | datetime | `customfield_10047` | timestamp of the claim (ISO-8601 UTC); powers stale detection |

> Field IDs are SCRUM-project configuration. If the fields are recreated in
> another project, replace the IDs with those project's values.

Claim invariant:

- `Assignee` stays **Nhat Nguyen Quang** (the human owner). Agents must NOT set
  assignee; the claim records ownership in `AI Agent` only.
- Each agent claims through its own Jira MCP, so web-only agents (e.g. ChatGPT)
  claim identically to local agents.
- The claim is **idempotent and race-guarded**:
  1. Read the issue and the current `AI Agent` value.
  2. If `AI Agent` is empty, set `AI Agent = <agent>`, set `Claimed At = <now>`,
     post a claim comment, and transition to `agent_running`.
  3. If `AI Agent` already equals this agent, do not overwrite; post a progress
     comment only.
  4. If `AI Agent` holds a *different* agent, this is a **double-claim**: stop,
     report `AI_AGENT_CLAIM_CONFLICT`, and do not overwrite the other agent's
     claim unless the human explicitly forces an override.
- A claim, like a work-tracking transition, is traceability only. It never grants
  G2, G4, G5, or G6 authority.

The PROGRESS REPORTER capability (skill `jira-progress-reporter`) reads the same
`AI Agent` / `Claimed At` fields to report, per agent, which tasks are claimed and
their status, and to flag stale (no update beyond the configured threshold) and
blocked tasks. Reporting is read-only and does not mutate task state.

## G3 async CI continuation

After creating or updating a Draft PR, the agent must not stop silently when CI is still running. It must keep the active work-tracking task in `validation_running` and choose the strongest available continuation mechanism for the next CI check:

1. webhook or event callback when available;
2. local sleep or poll loop when running as a capable local agent;
3. a two-minute sleep of the active thread when running as a ChatGPT chat connector;
4. another platform scheduler when its own runtime supports it;
5. manual checkpoint only when no async mechanism is available.

For a ChatGPT chat connector, record the repository, PR, expected head SHA, check-and-report-only boundary, and a two-minute wake time; then sleep the current thread for exactly two minutes. Do not create a scheduler task or automation. For every other continuation mechanism, the default next-check interval remains 3 minutes when the selected environment supports that cadence. If a non-ChatGPT platform supports only a slower cadence, use the supported cadence and report the limitation.

If the ChatGPT chat connector cannot sleep and wake the current thread, it must record a manual checkpoint rather than create a scheduler task or automation.

A CI wait task may check and report CI state only. It must not modify repository content, merge, deploy, reload runtime, release, touch production configuration, handle credentials, run migrations, or access production data unless a separate active approval or canonical route-specific authority covers that exact action.

When CI fails, the agent may repair only repository-fixable failures inside the approved G2 scope. Any repair commit invalidates prior CI, review, and G4-readiness evidence; the next G4 authority decision must bind to the latest head SHA after required CI is green.

## Approval command generation

The agent must generate the exact approval command from current gate evidence when the active route requires Human authority.

Format: `APPROVE <GATE> <approval_id> <scope_hash_16> <expires_at_utc>`

Rules:
- `approval_id`: `APPROVE_<GATE>_<task-id-short>_<YYYYMMDD>`
- `scope_hash`: Normalize envelope JSON (remove scope_hash, serialize UTF-8 JSON with sorted keys, arrays preserved, no insignificant whitespace), SHA-256, first 16 hex characters.
- The normalized envelope must include the gate, task ID when available, repository, branch or PR number when applicable, expected base SHA, expected head or release SHA when applicable, approved files or modules, authorized actions, excluded actions, required CI/deployment checks, and expiry.
- `expires_at`: ISO 8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`), no more than 24 hours after `issued_at`.
- Placement: Standalone fenced text block, one command per block.
- Humans do not invent gate tokens, artifact IDs, scope hashes, branches, file scope, or expiry.
- Do not generate a redundant Human command when a valid canonical route-specific standing/derived authority already satisfies the exact action.

## Exact user command presentation

Every approval, activation, retry, or exact command requested from the user
must be placed in a standalone fenced text block. Put one command in each
block. Do not place placeholders in a command represented as executable.

Do not copy full approval commands into commit messages, PR titles, connector
payloads, or long-lived comments. Evidence notes should use sanitized approval
metadata such as gate, approval ID, scope-hash prefix, and expiry, not the full
executable command.

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

- merge or auto-merge without a separately validated G4 authority source selected by the active canonical route;
- manual deployment, redeploy, runtime reload, or release without G5 manual-action scope;
- production configuration;
- credential rotation;
- production migration;
- production-data reads or writes;
- protected-branch direct push;
- force-push;
- branch deletion;
- shared-history rewrite;
- PR base change.

For `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`, the only standing-authority merge
exception is the exact validated `auto/* -> pre-prod` child merge. Promotion or
merge to `main` always remains Human G4.

CI success is evidence only. It never grants authority.