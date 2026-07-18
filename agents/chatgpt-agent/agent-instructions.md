# ChatGPT Agent Instructions for GWC-Governed Work

## Scope

These instructions apply to ChatGPT-style agents operating through conversation,
connectors, or project context where GWC governance is present or requested.

The default ChatGPT execution mode is `chat_connector_only` unless a trusted
local checkout, shell, filesystem, Git, and validator runner are explicitly
available in the active environment.

## Mandatory runtime banner

At the start of non-trivial GWC-governed work, report:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

If source instructions conflict, state the conflict rule and follow the
highest-priority active source unless a repository protected-base rule is
stricter.

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

No repository mutation is allowed until `Files WRITE` is explicit. A new write
path is scope drift and requires a regenerated approval request.

## Mandatory context boot

Before recommending, editing, or opening a Pull Request for a GWC-governed
project, the ChatGPT Agent must reconstruct context in this order:

1. System, platform, developer, and active project runtime instructions.
2. Target repository protected-base `AGENTS.md`.
3. Pinned GWC source or package:
   - `.gwc/gwc/AGENTS.md` when a GWC submodule exists;
   - `.governance/*` package files when the project consumes a generated package;
   - central `nhatnguyenquang1838-coder/gwc` source when directly operating on
     GWC.
4. `core/Coding_Project_Governance_v1.0.md`.
5. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`.
6. `core/Agent_Operating_Runtime_Contract_v1.0.md`.
7. `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`.
8. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`.
9. Active `projects/<project-id>/project-profile.yaml`.
10. Project instructions, extension, spec format, task files, package manifests,
    workflows, and relevant source files.

All repository files used for a gate decision must be fetched from one pinned
protected-base SHA. Do not combine policy, schema, template, validator, or task
artifacts from different revisions.

If repository evidence conflicts with conversation memory, repository evidence
wins unless the user explicitly overrides it without weakening a higher
authority.

## Execution mode declaration

At the start of repository-changing work, report:

```text
GWC BOOT: <PASS|BLOCKED> — execution_mode=<chat_connector_only|local_agent|repo_ci>
```

In `chat_connector_only` mode, do not invent file-system paths, task artifacts,
validator outputs, CI states, or DS Admin task transitions.

A connector-only agent may use an isolated writable filesystem and command
runner for fetched-file validation without claiming it has a trusted Git
checkout. The repository connector remains the source of truth. Every fetched
validator, schema, template, runbook, and source file must be bound to the exact
protected-base SHA and recorded in the gate evidence.

## Gate behavior

### G0_CONTEXT

The ChatGPT Agent may inspect repositories, files, pull requests, workflows,
issues, and connector metadata. This is read-only.

In chat-only mode, G0 may be reported as a **conversation-local gate packet**
when it cites the repository evidence used. When an isolated filesystem and
command runner are available, the agent must materialize the canonical G0
artifact under a unique task workspace and validate it instead of remaining at
a conversation-only packet.

### G1_ALIGNMENT

The ChatGPT Agent may reconstruct problem, scope, non-goals, options, risks,
acceptance criteria, and a recommended decision.

Do not report `G1_ALIGNMENT: PASS` unless one of these is true:

- the agent ran the exact protected-base `tools/validate_g01.py` against the
  exact task workspace with the matching protected-base schemas; or
- trusted CI/local evidence shows `validate_g01.py` returned `PASS` for the
  exact task workspace, repository, base SHA, branch, and scope hash.

Before reporting that a validator is unavailable, the agent must perform this
recovery sequence when connector reads, an isolated filesystem, and a command
runner are available:

1. Pin and re-verify the protected-base SHA.
2. Read the operational runbook from that SHA.
3. Fetch the required gate artifacts, schemas, templates, validators, and
   referenced sources from the same SHA.
4. Materialize them under a unique `/mnt/data/gwc_sessions/<session-id>/`
   workspace and preserve their repository paths.
5. Run the repository validator against the task workspace.
6. Repair and retry remediable artifact, transport, path, or schema errors while
   staying inside the current read/write scope.
7. Preserve the command, exit code, stdout/stderr, hashes, and limitations as
   validation evidence.

Only after the recovery sequence is technically impossible, a connector returns
a hard denial, or a real authority boundary is reached may the agent report:

```text
G1_ALIGNMENT: BLOCKED — exact validator evidence unavailable after artifact recovery
```

### G2_EXECUTION

In chat-only mode, do not create branches, update files, push commits, or open
Pull Requests unless trusted G0/G1 validator evidence, a valid execution
envelope, and the exact active approval command already exist.

When the user asks to apply a fix but gate evidence is missing, build the missing
read-only artifacts and validator evidence first. Do not stop merely because the
artifacts were not already present locally.

### G3_PR and later

Do not create or update a Draft PR without G3 evidence. Do not merge, deploy,
release, change production configuration, rotate credentials, or access
production data without explicit G4/G5/G6 authority.

## Artifact-driven gate continuation

The agent owns gate preparation. The human owns only the explicit authority
boundary.

For every gate transition, the agent must:

```text
Read protected-main runbook
→ resolve current gate and exact action
→ fetch current gate evidence from the pinned SHA
→ fetch matching schemas/templates/validators
→ materialize and validate in an isolated workspace
→ repair remediable evidence gaps
→ generate the next gate artifact and approval request
→ present the exact APPROVE command
→ stop only at the actual human-authority boundary or a hard denial
```

The minimum continuation artifacts are:

| Gate exit | Agent-generated next artifact |
|---|---|
| G0 READY | G1 intake, preflight, options, and decision inputs/artifacts |
| G1 PASS | G2 execution envelope plus approval request |
| G2 PASS | G3 delivery record bound to exact branch head SHA |
| G3 PASS | G4 merge approval request bound to exact PR/head SHA |
| G4 PASS | G5 deployment approval request bound to exact release/environment |
| G5 PASS | G6 production approval request bound to exact operation/environment |

For each transition, the agent must use the existing canonical mechanism before
creating a new one:

```text
Find existing → Reuse → Extend → Refactor → Replace only if required
```

Missing local files, unavailable raw-download transport, stale generated
artifacts, or a remediable schema error are recovery conditions, not automatic
workflow termination. A protected-branch write, merge, deployment, production
configuration, credential, migration, production-data operation, scope drift,
expired approval, or connector hard denial remains a real stop condition.

## Agent-generated approval commands

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

## Files READ / Files WRITE rules

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

## Context refresh trigger

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

## User-visible reporting

For GWC-governed work, show concise gate status and the recovery action actually
performed:

```text
GWC BOOT: PASS — execution_mode=chat_connector_only
G0_CONTEXT: READY — evidence: <repo/profile/task refs>
G1_ALIGNMENT: PASS — validator: <path, command, exit code, artifact hashes>
G2_EXECUTION: AWAITING_APPROVAL — <approval_request_id, scope_hash_16, expiry>
```

When blocked, report the exact failed recovery step, hard denial, or authority
boundary. Do not use `validator unavailable` as a generic reason when connector
fetch plus isolated local validation was possible.

Do not expose hidden reasoning. Report evidence, blockers, decisions, and next
allowed action.

## Project context discipline

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

## Safety boundary

Tool availability does not grant authority. A user instruction such as
`apply fix`, `continue`, or `approve` does not replace G0/G1 artifacts,
validator evidence, G2 execution envelope, G3 delivery record, or G4/G5/G6 human
authority.

The ChatGPT local filesystem may be used for artifacts, reports, patch bundles,
and fetched-file validation workspaces. It is not repository source of truth
unless it contains a verified full checkout with Git metadata and the expected
base SHA. Connector-fetched files may still be used for task-scoped validation
when their exact repository path, protected-base SHA, blob SHA, and content hash
are preserved in evidence.
