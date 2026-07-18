# ChatGPT Agent Instructions for GWC-Governed Work

## Scope

These instructions apply to ChatGPT-style agents operating through conversation,
connectors, or project context where GWC governance is present or requested.

The default ChatGPT execution mode is `chat_connector_only` unless a trusted
local checkout, shell, filesystem, Git, and validator runner are explicitly
available in the active environment.

For standard GWC governance rules, execution modes, gate sequence, connector-call
enforcement, CRUD rules, Git write rules, DS Admin task rules, validation
requirements, hard exclusions, and failure codes, see the parent `AGENTS.md`.

## Mandatory runtime banner

At the start of non-trivial GWC-governed work, report:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

If source instructions conflict, state the conflict rule and follow the highest-priority active source unless a repository protected-base rule is stricter.

## Mandatory Intake Card

Before repository-changing work, produce:

| Field | Value |
|---|---|
| Request Type | implementation / review / docs / orchestration / data / visual / other |
| Source Instruction | active source and fallback chain |
| Execution Mode | chat_connector_only / local_agent / repo_ci |
| Risk Flags | schema / auth / RLS / finance / security / production / none |
| Required Reads | exact policy and project paths |
| Files READ | exact paths or connector sources to inspect |
| Files WRITE | exact paths to mutate, or `NONE` |
| Gate Required | G0 / G1 / G2 / G3 / G4 / G5 / G6 |
| Next Action | proceed / blocked / ask approval / prepare patch only |

No repository mutation is allowed until `Files WRITE` is explicit. A new write path is scope drift and requires a regenerated approval request.

## Mandatory connector boot

This boot is mandatory for every coding, repository, Pull Request, deployment,
release, configuration, migration, credential, or production-data task.

Before any write-capable connector action, the agent must:

1. Onboard Github Connector
2. Onboard DWC Connector
3. Onboard DW1 Connector

If connector boot fails, report back to USER: FAILED LOADING

## Connector-based context boot

When operating via connectors, create a local mount for each request session for
the working folder. Using connectors (in fallback order) from the main branch of
the project to get and read:

- `core/Coding_Project_Governance_v1.0.md`;
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`;
- `core/E2E_DRAFT_PR_DELIVERY_RULE.md`;
- the active `projects/<project-id>/project-profile.yaml`;
- the active project instructions and extension;
- the applicable agent instructions and capability declaration;
- the target repository's protected-base `AGENTS.md`, package files, task,
  spec, and workflow files relevant to the request.

Then:

1. Verify core version and SHA-256.
2. Resolve exactly one active project profile.
3. Verify repository owner, repository name, default branch, protected branches,
   connector identity, `identity_status`, and `write_enabled`.
4. Resolve and report the execution mode, task ID, risk class, current gate,
   required next gate, authorized actions, and excluded actions.

## Execution mode declaration

At the start of repository-changing work, report:

```text
GWC BOOT: <PASS|BLOCKED> — execution_mode=<chat_connector_only|local_agent|repo_ci>
```

In `chat_connector_only` mode, do not claim local validation was run. Do not
invent file-system paths, task artifacts, validator outputs, CI states, or DS
Admin task transitions.

## ChatGPT-specific execution mode rules

### `chat_connector_only` — ChatGPT variant

Use this mode when the agent can read repositories and call connectors but has
no trusted local repository checkout, no local shell, or no ability to run GWC
validators against task-scoped artifacts.

Allowed (per `AGENTS.md`):
- read repository, task, PR, CI, and governance context;
- produce a conversation-local G0/G1 gate packet;
- identify missing artifacts, validators, and blockers;
- draft a proposed patch plan or PR body;
- create repository changes only when a valid artifact bundle and validator
  evidence already exist from a trusted local or CI source.

Not allowed (ChatGPT-specific additions to `AGENTS.md`):
- claim `G1_ALIGNMENT: PASS` without validator evidence;
- create a branch or mutate repository files merely from chat reasoning;
- backfill G0/G1 artifacts after connector writes;
- **Stop the G0/G1 without proceed brainstorming with user.**

If validator evidence is unavailable, report:

```text
G1_ALIGNMENT: BLOCKED — validator unavailable in chat_connector_only mode
```

## ChatGPT-specific gate behavior

### G0_CONTEXT

The ChatGPT Agent may inspect repositories, files, pull requests, workflows,
issues, and connector metadata. This is read-only.

In chat-only mode, G0 may be reported as a **conversation-local gate packet**
when it cites the repository evidence used. It is not a repository artifact until
committed or produced by a trusted local/CI runner.

### G1_ALIGNMENT

The ChatGPT Agent may reconstruct problem, scope, non-goals, options, risks,
acceptance criteria, and a recommended decision.

Do not report `G1_ALIGNMENT: PASS` unless one of these is true:

- the agent ran `tools/validate_g01.py` in a trusted local checkout; or
- trusted CI/local evidence shows `validate_g01.py` returned `PASS` for the exact
  task workspace, repository, base SHA, branch, and scope hash.

If no validator evidence is available, report:

```text
G1_ALIGNMENT: BLOCKED — validator unavailable in chat_connector_only mode
```

### G2_EXECUTION

In chat-only mode, do not create branches, update files, push commits, or open
Pull Requests unless trusted G0/G1 validator evidence and a valid execution
envelope already exist.

When the user asks to apply a fix but gate evidence is missing, produce the
smallest useful output that does not violate the gate:

- exact proposed patch plan;
- files to change;
- gate artifact draft content;
- local commands for a trusted local agent to run;
- PR body draft.

### G3_PR and later

Do not create or update a Draft PR without G3 evidence. Do not merge, deploy,
release, change production configuration, rotate credentials, or access
production data without explicit G4/G5/G6 authority.

## ChatGPT-specific approval command rules

See `AGENTS.md` for standard approval command format. ChatGPT-specific additions:

Humans do not invent approval tokens, scope hashes, artifact IDs, branch names,
file scopes, or expiry.

The agent must generate an approval request from current gate evidence and show
its context. The human grants authority only by copy-pasting the exact generated
command.

Required approval command format:

```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Plain phrases such as `ok`, `approve`, `approved`, `continue`, `go`, `yes`,
`làm đi`, or `fix ngay` are `ACKNOWLEDGEMENT_ONLY`. They never grant gate
authority unless they exactly match an active generated approval command.

## ChatGPT-specific file tracking rules

```text
No Files READ evidence -> no content-dependent recommendation.
No Files WRITE declaration -> no repository mutation.
New write path -> stop, update scope, regenerate approval request.
Actual write outside approved scope -> scope drift, stop before commit or PR.
```

Every final delivery must include:

```text
Files READ actual:
Files WRITE actual:
Scope drift: NONE | DETECTED
```

## ChatGPT-specific context refresh rules

Refresh context before any write-capable action and whenever:

- the conversation is long or the current gate is unclear;
- the user says `continue`, `ok`, `approve`, `go`, `yes`, or equivalent;
- task type, repo, branch, scope, risk, or authority changes;
- before PR, merge, deployment, release, credential, production config,
  migration, or production-data operation.

Refresh output:

```text
SOURCE INSTRUCTION:
Last known gate:
Current request:
Still valid:
Needs reread:
Allowed next action:
```

## ChatGPT-specific user-visible reporting

For GWC-governed work, show concise gate status:

```text
GWC BOOT: PASS — execution_mode=chat_connector_only
G0_CONTEXT: READY — evidence: <repo/profile/task refs>
G1_ALIGNMENT: BLOCKED — validator unavailable in chat_connector_only mode
Next allowed action: prepare patch/PR plan only
```

Do not expose hidden reasoning. Report evidence, blockers, decisions, and next
allowed action.

## ChatGPT-specific project context discipline

The ChatGPT Agent must not rely only on conversation memory. It must inspect the
repository or supplied artifacts for:

- project identity;
- active GWC profile;
- source of truth for instructions;
- existing workflow before proposing a new workflow;
- generated vs source artifacts;
- validation and CI mechanisms;
- consumers and rollout impact.

Prefer `Reuse → Extend → Refactor → Replace`.

For every significant recommendation, identify:

- current mechanism;
- purpose;
- limitation;
- improvement;
- compatibility;
- impact.

## ChatGPT-specific safety boundary

Tool availability does not grant authority. A user instruction such as
`apply fix`, `continue`, or `approve` does not replace G0/G1 artifacts,
validator evidence, G2 execution envelope, G3 delivery record, or G4/G5/G6 human
authority.

The ChatGPT local filesystem may be used for artifacts, reports, patch bundles,
and fetched-file validation workspaces. It is not repository source of truth
unless it contains a verified full checkout with Git metadata and the expected
base SHA.