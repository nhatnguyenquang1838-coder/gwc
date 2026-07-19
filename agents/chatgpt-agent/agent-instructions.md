# ChatGPT Agent Instructions for GWC-Governed Work

## Purpose and authority

These instructions apply to ChatGPT-style agents operating through conversation,
connectors, project context, or a trusted local checkout. They are an additive
runtime overlay on the parent `AGENTS.md`.

The parent file remains canonical for authority order, shared boot, execution
modes, gate lifecycle, connector-call enforcement, CRUD and Git rules, DS Admin
task rules, validation, exclusions, and failure codes. If this overlay conflicts
with the parent, follow the parent or any higher-priority instruction.

## Capability-based execution mode

Choose exactly one execution mode from verified capabilities, not from the
ChatGPT product name or conversation surface:

- Use `local_agent` when the active environment has a trusted full checkout,
  shell, filesystem, Git, isolated worktree or session support, and can run the
  protected-base GWC validators.
- Use `chat_connector_only` when repository connectors are the source of truth
  and no trusted full checkout is available, even if an isolated filesystem and
  command runner can validate fetched artifacts.
- Use `repo_ci` only inside the repository's CI runner.

Do not downgrade a capable ChatGPT agent to `chat_connector_only`. Do not claim
`local_agent` merely because a temporary filesystem or command runner exists.

## Mandatory runtime banner

At the start of non-trivial GWC-governed work, report:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

If sources conflict, state the applicable authority rule. Repository evidence
from the pinned protected base overrides conversation memory unless an explicit
user instruction validly changes scope without weakening higher authority.

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
path is scope drift and requires refreshed artifacts and approval.

## Context boot and connector fallback

Run the shared boot from `AGENTS.md`, including the protected-base project
profile, project instructions, extension, task/spec/workflow context, and:

- `core/Agent_Operating_Runtime_Contract_v1.0.md`;
- `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`;
- this ChatGPT overlay.

Bind policy, schemas, templates, validators, task evidence, and decisions to one
exact protected-base SHA. Do not combine gate evidence from different revisions.

Use repository access in the active profile's declared precedence order. For the
`gwc` profile that is GitHub, then DWC, then DW1. Use the first available,
authorized route; record fallback and continue when an earlier connector is
unavailable. Do not require onboarding every declared connector, and do not
report a generic loading failure when another verified route or the trusted
local checkout can supply the required evidence.

In `local_agent`, the verified checkout is repository source of truth for the
pinned base and active guarded branch. Connector calls are needed only for facts
or actions that the local checkout cannot prove or perform, such as DS Admin
state, remote PR state, or CI evidence.

In `chat_connector_only`, the repository connector remains source of truth. A
local isolated filesystem may hold fetched validation inputs, but it is not a
trusted checkout unless Git metadata and the expected base SHA are verified.

## ChatGPT gate behavior

### G0_CONTEXT

Repository, PR, workflow, task, and connector inspection is read-only. When an
isolated filesystem and command runner are available, materialize and validate
the canonical G0 artifact instead of stopping at a conversation-local packet.

### G1_ALIGNMENT

Reconstruct problem, scope, non-goals, options, risks, acceptance criteria, and
the explicit decision. Never report `G1_ALIGNMENT: PASS` unless:

- the exact protected-base `tools/validate_g01.py` passed against the matching
  task workspace and schemas; or
- trusted local or CI evidence proves that PASS for the same task, repository,
  base SHA, branch, and scope hash.

Before reporting validator evidence unavailable in `chat_connector_only` when
connector reads, an isolated filesystem, and a command runner exist:

1. Pin and re-verify the protected-base SHA.
2. Read the protected-base operational runbook.
3. Fetch the required gate artifacts, schemas, templates, validators, and
   referenced sources from the same SHA.
4. Materialize them under a unique `/mnt/data/gwc_sessions/<session-id>/`
   workspace while preserving repository paths and source hashes.
5. Run the repository validator against the task workspace.
6. Repair and retry remediable artifact, transport, path, or schema errors within
   the declared scope.
7. Preserve command, exit code, output, hashes, and limitations as evidence.

Only after that recovery is technically impossible, a connector returns a hard
denial, or an authority boundary is reached may the agent report:

```text
G1_ALIGNMENT: BLOCKED - exact validator evidence unavailable after artifact recovery
```

### G2_EXECUTION

Do not create a branch, worktree, update, commit, push, or PR without matching
G0/G1 evidence, a valid execution envelope, and the exact active approval when
the runtime contract requires it. Missing gate files are preparation work: build
and validate them before treating the request as blocked.

### G3_PR and later

Follow the parent gate contract. G3 permits a Draft PR only. G4 merge, G5
status/deployment verification, and G6 production authority remain separate
exact human approvals. Before G4 merge execution, verify that the PR is no
longer Draft and is ready for review. If the connector cannot mark it ready,
report a ready-for-review blocker instead of invoking merge.

## Artifact-driven gate continuation

The agent owns gate preparation; the human owns explicit authority boundaries.
For each transition:

```text
Read protected-base runbook
-> resolve current gate and exact action
-> obtain current evidence from the pinned SHA
-> obtain matching schemas, templates, and validators
-> materialize and validate in an isolated workspace
-> repair remediable evidence gaps
-> generate the next gate artifact and approval request
-> present the exact APPROVE command
-> stop only at a real human-authority boundary or hard denial
```

| Gate exit | Agent-generated next artifact |
|---|---|
| G0 READY | G1 intake, preflight, options, and decision inputs/artifacts |
| G1 PASS | G2 execution envelope plus approval request |
| G2 PASS | G3 delivery record bound to exact branch head SHA |
| G3 PASS | G4 merge approval request bound to exact PR/head SHA and PR-ready status |
| G4 PASS | G5 status/deployment verification request bound to exact commit/environment/checks |
| G5 PASS | G6 production approval request only when production operation scope exists; otherwise record `not_applicable` |

Use the existing canonical mechanism first:

```text
Find existing -> Reuse -> Extend -> Refactor -> Replace only if required
```

Missing local files, transport failures, stale generated artifacts, and
remediable schema errors are recovery conditions. A protected-branch write,
merge, deployment, production configuration, credential, migration,
production-data operation, scope drift, expired approval, or
`connector hard denial` is a real stop condition.

## Agent-generated approval commands

The agent generates approval identifiers, scope hashes, branch names, file
scope, expiry, and the exact command. The human grants authority only by sending
the active command exactly:

```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Plain acknowledgements such as `ok`, `approve`, `continue`, `go`, `yes`, or
equivalents are `ACKNOWLEDGEMENT_ONLY` and do not grant gate authority.

Do not copy full executable approval commands into connector payloads, commit
messages, PR titles, or long-lived comments. Use sanitized metadata: gate,
approval ID, scope-hash prefix, expected SHA, and expiry.

## File tracking and context refresh

```text
No Files READ evidence -> no content-dependent recommendation.
No Files WRITE declaration -> no repository mutation.
New write path -> refresh scope and approval before writing.
Actual write outside approved scope -> stop before commit or PR.
```

For G5, do not infer a manual deploy/reload from the gate name. If deployment is
integrated into GitHub Actions or Vercel checks, G5 is status verification only:
inspect the relevant post-merge workflow, deployment check, runtime status, or
tool surface for the exact approved commit. Manual deploy, redeploy, release,
or runtime reload requires explicit G5 manual-action scope.

Refresh the active source, gate, task, repository, branch, scope, risk, and
authority before every write-capable action and whenever the user says to
continue or the context changes materially.

Every delivery reports:

```text
Files READ actual:
Files WRITE actual:
Scope drift: NONE | DETECTED
```

## User-visible reporting

Show concise status with evidence and the actual recovery or approval boundary:

```text
GWC BOOT: PASS - execution_mode=<mode>
G0_CONTEXT: READY - evidence: <repo/profile/task refs>
G1_ALIGNMENT: PASS - validator: <path, command, exit code, hashes>
G2_EXECUTION: AWAITING_APPROVAL - <request id, scope hash, expiry>
```

Do not expose hidden reasoning. Report evidence, decisions, blockers, and the
next allowed action. Never use `validator unavailable` generically when exact-SHA
fetch and isolated validation are possible.

## Safety boundary

Tool availability, a user request, or CI success does not replace gate artifacts
or grant unrelated authority. Never invent repository paths, task artifacts,
validator output, CI state, connector identity, or DS Admin transitions. DS
Admin transitions must be legal State Engine transitions and should be updated
at each gate boundary; late reconciliation must be disclosed as late.
