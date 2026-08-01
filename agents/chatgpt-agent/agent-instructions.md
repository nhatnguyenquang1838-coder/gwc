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

## Vietnamese-first GWC responses

In GWC project chat, ChatGPT-style agents must respond Vietnamese-first. Use English only for exact commands, gate identifiers, file paths, branch names, commit SHAs, tool names, code, YAML, JSON, API identifiers, and other machine-readable content.

Status reports, blockers, evidence summaries, recommendations, and next actions should be written primarily in Vietnamese.

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
- `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md`;
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

## Kiro spec and task-runtime parity

For significant governed work moving from planning toward implementation, follow `core/KIRO_SPEC_DRIVEN_DELIVERY_RULE_v1.0.md` and use the existing local-agent task mechanism instead of producing conversation-only planning artifacts.

Before entering G2, a ChatGPT-style agent must:

1. resolve or create exactly one AgentOps/DS Admin task for the outcome;
2. read the live task state contract and use legal idempotent transitions;
3. transition or verify that task in `agent_running` during G0/G1 preparation;
4. materialize the canonical workspace under `.gwc/tasks/<task-id>/g0`, `g1`, and `g2`;
5. bind task ID, repository, protected-base SHA, branch, and scope hash consistently;
6. run or cite the protected-base G0/G1 validator before requesting G2;
7. synchronize DS Admin state at later gate boundaries.

In `chat_connector_only`, local preparation may use a unique isolated `/mnt/data/gwc_sessions/<session-id>/` workspace. Persisting those artifacts to the repository remains a G2 write.

Kiro specs, task creation, `agent_running`, and valid `.gwc` artifacts are traceability evidence only. They never grant repository write, Draft PR, merge, deploy, release, production configuration, credential, migration, or production-data authority.

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

For every gate-scoped action, validate a task-scoped action packet with
`tools/validate_gate_action.py`. The packet must bind task, repository,
base/head SHA, branch, gate, action, scope hash, expiry, actor, and evidence
readback. A Jira status or connector response alone is never sufficient
authority evidence.

Use `core/task-lifecycle/gate-transition-map.yaml` for state readback. G3
review, G4 merge, G5 status/deployment, and conditional G6 production states
are separate; `VALIDATION_PASSED` must not be treated as final completion.

### G3_PR and later

Follow the parent gate contract. G3 permits a Draft PR and may complete the
metadata transition from Draft to Ready for review after G3 `PASS` when a
connector action exists and the latest head SHA, CI, review closure, and scope
checks are valid. This transition is not merge approval.

G4 merge remains a separate exact human approval. Read-only `G5_STATUS_VERIFY`
after G4 merge is automatic and does not require a human token. Manual deploy,
redeploy, release, publish, runtime reload, and G6 production authority remain
separate exact human approvals. Before G4 merge execution, verify that the PR is
no longer Draft and is ready for review. If the connector cannot mark it ready,
report a ready-for-review blocker instead of invoking merge.

## G4/G5 GitHub evidence flow

When `.github/workflows/g4-g5-evidence.yml` exists, ChatGPT-style agents must
use the repository event chain below rather than inventing conversation-local
evidence:

```text
G3 exact-head PASS and Ready-for-Review readback
-> exact human G4 PR comment
-> validated G4 authority Actions artifact
-> sanitized `gwc:g4-authority-receipt` PR comment
-> separately authorized merge action
-> GitHub `pull_request.closed` event with `merged=true`
-> G4 merge-proof Actions artifact
-> `gwc:g4-merge-proof` PR comment
-> exact merge-SHA required workflows on `main`
-> canonical G5 Actions artifact
-> `gwc:g5-status` PR trace comment
-> optional Jira/Slack projections
```

### G4 authority handling

The only executable G4 authority source is the original human PR comment in the
exact format:

```text
APPROVE G4 <approval_id> <scope_hash_16> <expires_at_utc>
```

Before using it, verify that the PR is open, no longer Draft, the commenter has
repository write/maintain/admin authority, the command is unexpired, and the
approved head equals the current PR head. The bot-generated
`gwc:g4-authority-receipt` comment and its GitHub Actions artifact are receipts
only; they never create authority and never authorize G5 manual actions.

The evidence workflow must not merge the PR. Merge remains a separate
write-capable action and must use the current exact approved head SHA. After a
successful merge, the GitHub `pull_request.closed` event with `merged=true` is
the source for `gwc:g4-merge-proof`. If approved head and merged head differ,
the evidence chain is stale and fails closed.

### G5 post-merge handling

G5 status verification starts only after a merge commit exists. G4 authority or
merge proof alone never satisfies G5. Resolve the required `push` workflows on
`main` for the exact merge commit SHA and classify only as:

```text
success
failure
CI_PENDING
CONNECTOR_OBSERVABILITY_INCOMPLETE
SHA_MISMATCH
```

The canonical machine evidence is the GitHub Actions artifact produced by the
G4/G5 evidence workflow. The `gwc:g5-status` PR comment is human traceability
only. Jira and Slack are `projection_only` and cannot replace the human G4
comment, GitHub merge event, exact-SHA workflow evidence, or Actions artifact.

Do not commit post-merge evidence back to the merged branch and do not create a
recursive evidence PR. In `chat_connector_only`, inspect the PR comments,
workflow runs, jobs, and artifacts through GitHub connector readback. Never
fabricate a G5 comment or PASS when the PR is still Draft/unmerged, required
workflows are non-terminal, or the exact merge-SHA evidence chain is absent.

## ChatGPT thread sleep for CI continuation

When running as a ChatGPT chat connector and a future CI check is needed, sleep the current thread for exactly two minutes. Do not create a scheduler task or automation.

Before sleeping the thread, record:

- repository and PR number;
- expected head SHA when available;
- allowed action boundary, normally check and report only;
- excluded actions: no merge, deploy, reload, release, production configuration, credentials, migrations, or production data;
- two-minute wake time.

When the thread wakes, verify the latest PR head SHA before checking or reporting CI. If the platform cannot sleep and wake the current thread, record a manual checkpoint; do not substitute a scheduler task or automation.

A resumed ChatGPT thread may fix and commit only when an active G2 scope explicitly authorizes repository repair. It must never merge, deploy, reload runtime, or perform production operations from the resumed check.

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
| G3 PASS | G4 merge approval request after marking Draft PR ready for review when supported; request is bound to exact PR/head SHA and PR-ready status |
| G4 PASS | G5 deployment approval request only for manual G5 action; otherwise automatic read-only G5 status verification bound to exact commit/environment/checks |
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
tool surface for the exact approved commit. Read-only `G5_STATUS_VERIFY` is
automatic after G4 merge. Manual deploy, redeploy, release, publish, or runtime
reload requires explicit G5 manual-action scope.

For post-merge verification, first attempt exact lookup using `event=push`,
`branch=main`, and `head_sha=<merge_sha>` or equivalent connector parameters. If
the connector surface does not support those filters or returns empty results,
fall back to a known `run_id` and direct jobs/artifacts lookup. Empty PR-filtered
results without run-id/artifact fallback evidence must be classified
`CONNECTOR_OBSERVABILITY_INCOMPLETE`, not `CI_PENDING`.
`CI_PENDING` is reserved only when a run is found but has not yet completed.

## Presentation contract

After G1, when a human-review HTML artifact is generated, follow the presentation contract:

- Local agent: return concise summary plus clickable or served local HTML path.
- Chat connector: return concise summary plus HTML artifact or link.
- Slack delivery: use the existing root task thread and include concise summary plus same HTML artifact or link.
- If presentation conflicts with canonical artifacts, mark it `STALE` or `INVALID` and do not alter gate authority.
- The HTML must be self-contained, mobile-first, printable, dark-mode compatible, and must not depend on remote JavaScript, CSS, fonts, or external runtime dependencies.

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
