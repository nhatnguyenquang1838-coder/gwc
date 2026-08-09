# Agent Operating Runtime Contract v1.0

## Purpose

This contract converts project-level operating guides into centralized GWC behavior for ChatGPT-style agents, DWC, local coding agents, and project consumer agents.

It addresses four failure modes:

1. Long conversations losing active instructions.
2. Plain acknowledgements such as `ok`, `approve`, or `continue` being mistaken for gate authority.
3. Project-local instructions drifting without central governance.
4. Agent-executed governed work starting before task intake, claim, and readback are complete.

This contract is additive. It does not replace `Coding_Project_Governance_v1.0`, `GATE_LIFECYCLE_CONTRACT_v1.0`, project profiles, approval envelopes, or stricter project instructions.

## Mandatory runtime banner

For any non-trivial repository, PR, review, docs, orchestration, configuration, release, deployment, or production-data task, the agent must print:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

When sources conflict, the agent must report the conflict rule and follow the highest-priority active source.

## GWC boot default

GWC boot is enabled by default for any GWC-governed request, including repository, PR, coding, governance, delivery, validation, Jira projection, Slack projection, CI, branch, worktree, package, release, deployment, migration, credential, production configuration, production data, or explicit GWC workflow request.

The agent may treat GWC as disabled only when the user gives an explicit opt-out phrase such as:

```text
NO GWC
Không GWC
loại bỏ GWC
ignored GWC
```

Ambiguous speed or simplicity requests such as `quick`, `simple`, `just do`, `skip ceremony`, `minor fix`, `hotfix`, or `rescue` do not disable GWC. They may select a bounded workflow, but boot, intake, claim, source refresh, file scope, and gate authority still apply.

## Chat-only exploration

G0/G1 brainstorming is conversation-local by default. It may produce an
informal intake, options, preflight discussion, and decision candidate without
persisting artifacts, creating a task, or generating an approval token. Label
this state `CHAT_ONLY_PREPARATION` and grant no execution authority.

Formal G0/G1 artifacts, active-provider task creation or claim, and the exact G2
approval command are required when the user explicitly requests transition
to G2 or asks for a write-capable action, except when a canonical route-specific
standing/derived authority source already satisfies the exact G2 action.

## Intake Card

Before repository-changing work, the agent must produce an Intake Card:

| Field | Required content |
|---|---|
| Request Type | implementation / review / docs / orchestration / data / visual / other |
| Source Instruction | exact active instruction source and fallback chain |
| Execution Mode | chat_connector_only / local_agent / repo_ci |
| Executor Type | agent / human / pair / ci / recovery |
| Work Item | active Jira/DS/Admin/task ID, or why planning-only work has no task yet |
| Agent Claim | required for executor_type=agent; otherwise not_applicable |
| Claim Readback | PASS / BLOCKED / CONFLICT / not_applicable |
| Risk Flags | schema / auth / RLS / finance / security / production / none |
| Required Reads | exact policy and project paths |
| Files READ | exact file paths or connectors to inspect |
| Files WRITE | exact file paths to mutate, or `NONE` |
| Gate Required | G0 / G1 / G2 / G3 / G4 / G5 / G6 |
| Next Action | proceed / blocked / ask approval / prepare patch only |

No repository mutation is allowed until `Files WRITE` is explicit. Writing outside `Files WRITE` is scope drift and requires a new approval request.

## Agent-only task claim

When `executor_type=agent`, the work-tracking task claim is mandatory before any governed write-capable action, including branch creation, worktree creation, repository file update, commit, push, PR creation/update, Jira transition, Slack projection, gate movement, merge check, or release/deploy/config/data action.

For Jira-backed GWC tasks, the agent must:

1. read current task state;
2. verify the task is unclaimed or already claimed by the same active agent;
3. set existing fields `AI Agent` and `Claimed At` when unclaimed;
4. add an intake or claim trace comment when the connector supports it;
5. transition to the appropriate active state when required by the project workflow;
6. read back the task;
7. stop before governed writes unless `AI Agent`, `Claimed At`, and active task state match the current agent execution.

This requirement applies to agent execution only. Empty `AI Agent` or `Claimed At` fields do not invalidate human-owned or human-executed work. Jira remains planning and projection evidence; Jira status or field values never grant G0-G6 authority by themselves.

If the task is already claimed by another active agent, stop with:

```text
AI_AGENT_CLAIM_CONFLICT
```

If the claim cannot be written or read back, stop with:

```text
AGENT_TASK_CLAIM_BLOCKED
```

If agent work already occurred before claim, do not backdate `Claimed At`. Record a retrospective correction and use the correction timestamp only.

## Files READ / Files WRITE discipline

Rules:

```text
No Files READ evidence -> no content-dependent recommendation.
No Files WRITE declaration -> no repository mutation.
New write path -> stop, update scope, regenerate approval request.
Actual write outside approved scope -> scope drift, stop before commit or PR.
```

Every delivery report must include:

```text
Files READ actual:
Files WRITE actual:
Scope drift: NONE | DETECTED
```

## ChatGPT connector-only Git rule

In ChatGPT `chat_connector_only` mode:

- GitHub/Git/DWC connectors are the source of truth for repository state.
- `/mnt/data` may be used for artifacts, reports, patch bundles, and fetched-file validation workspaces.
- `/mnt/data` must not be treated as repository source of truth unless it contains a verified full checkout with Git metadata and expected base SHA.
- Local `git clone`, `git pull`, `git checkout`, `git push`, branch, PR, merge, or CI commands in the container must not be used as authority.
- A trusted checkout is NOT required to use an authorized repository write connector after the matching gate evidence, scope, claim, and authority have been validated.

## Connector-runtime capability decomposition

Execution mode and action capability are separate decisions. `chat_connector_only`
means repository connectors remain source of truth; it does not mean the runtime
is incapable of materialization, validation, or authorized connector writes.

Resolve these capabilities independently:

```text
repository_read_capability
local_materialization_capability
validator_execution_capability
repository_write_connector_capability
```

Rules:

1. Connector file content/text/blob readback plus a writable isolated filesystem
   is sufficient to materialize validation input. A mounted connector file is
   not required.
2. If connector reads, isolated filesystem, and a command runner are available,
   the agent MUST fetch the exact protected-base validators/schemas/referenced
   sources and run the validator before reporting validator unavailability.
3. Absence of a trusted local checkout keeps the mode `chat_connector_only`; it
   does not cancel independently available validator or repository-write
   connector capabilities.
4. After G0/G1 trusted validation and exact G2/route-specific authority, an
   authorized GitHub/repository connector MAY create the guarded branch and
   perform scoped writes. The connector action is the repository executor;
   local Git is not required.
5. Missing one capability blocks only actions that require that capability.
   Do not collapse capability absence into a generic execution-mode blocker.

Canonical connector-only ordering:

```text
EXACT CONNECTOR READBACK
→ LOCAL/MNT MATERIALIZATION
→ VALIDATOR EXECUTION
→ EXACT G2 OR ROUTE-SPECIFIC STANDING AUTHORITY
→ GUARDED REPOSITORY CONNECTOR WRITE
→ EXACT READBACK / CI
```

## Route-specific authority precedence

Generic gate prose defines the default authority route. A canonical
route-specific policy can satisfy a gate with bounded standing/derived authority
only for the exact action and bindings it validates. Route-specific authority
does not bypass the gate; it supplies that gate's authority source.

For `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`:

```text
DAG_SELECT
→ AUTHORITY_RESOLVE
→ AUTHORIZED_READY
→ derived child G2
→ auto/* child delivery to exact pre-prod
→ exact-head standing G4 for auto/* → pre-prod
→ Human G4 for pre-prod → main
```

Required semantics:

- `pre-prod` is the autonomous child execution/integration base even when the
  repository default branch is `main`.
- `main` remains governance/release/promotion context for this route.
- A valid trusted parent manifest/authority receipt plus valid derived child G2
  replaces a redundant Human G2 request for that exact allowlisted child scope.
- A valid standing exact-head G4 replaces a redundant Human G4 request only for
  the bounded `auto/* → pre-prod` child merge.
- Promotion/merge to `main` always requires Human G4.
- If route-specific authority is missing, stale, untrusted, mismatched, or
  expired, fail closed; do not silently infer authority from this contract.

## Context refresh trigger

The agent must refresh context before any write-capable action and whenever one of these occurs:

- long conversation or unclear current gate;
- user says `continue`, `ok`, `approve`, `go`, `yes`, or equivalent;
- task type, repo, branch, scope, risk, or authority changes;
- executor type changes, or an agent claim is missing, stale, conflicting, or unreadable;
- protected-base drift is detected; classify the changed files and refresh only
  the evidence required by `SAFE_CONTINUE`, `REVALIDATE`, `REAPPROVE`, or
  `STOP`.
- before PR, merge, deployment, release, credential, production config, migration, or production-data operation.

Refresh output:

```text
SOURCE INSTRUCTION:
Last known gate:
Current request:
Executor Type:
Claim Readback:
Still valid:
Needs reread:
Allowed next action:
```

## Agent-generated approval request

Humans do not invent gate tokens, artifact IDs, scope hashes, branches, file scope, or expiry.

The agent must generate an approval request from current gate evidence and show the full context. The human grants authority only by copy-pasting the exact generated command when the active route requires human authority.

Approval context must include:

| Field | Required |
|---|---|
| Gate | yes |
| Approval Request ID | yes |
| Repository | yes |
| Base Branch | yes |
| Base SHA | yes |
| Working Branch | when applicable |
| Scope Hash | yes |
| Scope Hash Short | yes |
| Files READ | yes |
| Files WRITE | yes |
| Authorized Actions | yes |
| Excluded Actions | yes |
| Expires At | yes |

Generated command format:

```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

The command must be placed in a standalone fenced `text` block. The agent must not ask the human to construct or edit the command.

## Proactive approval generation on gate exit

Upon completing any gate's exit criteria, the agent must immediately resolve the
next gate's active authority source. Generate a human approval request only when
the active route requires human authority for that exact next action.

The agent must:

1. Confirm the current gate's exit criteria are fully satisfied and validated.
2. Resolve whether the next gate uses human authority or a canonical trusted
   standing/derived authority source.
3. Generate the next gate's entry artifact/decision using current evidence.
4. If human authority is required, present the generated approval command in a
   standalone fenced text block and wait for the user.
5. If trusted standing/derived authority already satisfies the exact action,
   continue without asking for a redundant human token.

The agent must never manufacture standing authority. Missing or invalid standing
authority fails closed at the same gate boundary.

## Acknowledgement-only phrases

These inputs are never gate authority by themselves:

```text
ok
okay
yes
y
approve
approved
continue
go
làm đi
fix ngay
apply
```

They are `ACKNOWLEDGEMENT_ONLY` unless they exactly match an active agent-generated approval command.

## Validation honesty

The agent must not say `pass`, `done`, `merged`, `deployed`, `validated`, or equivalent unless supported by tool, validator, CI, or repository evidence.

Delivery reports must separate:

```text
Validation performed:
Validation skipped:
Evidence:
Limitations:
```

## PR defaults

Unless stricter project or route-specific rules say otherwise:

- create Draft PR only;
- do not request reviewers automatically;
- do not mark ready for review automatically;
- do not merge or enable auto-merge without valid G4 authority from the active canonical authority source;
- CI success is evidence only, not authority;
- Human G4 is always required for merge/promotion to `main`.
