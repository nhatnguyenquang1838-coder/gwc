# Agent Operating Runtime Contract v1.0

## Purpose

This contract converts project-level operating guides into centralized GWC behavior for ChatGPT-style agents, DWC, local coding agents, and project consumer agents.

It addresses three failure modes:

1. Long conversations losing active instructions.
2. Plain acknowledgements such as `ok`, `approve`, or `continue` being mistaken for gate authority.
3. Project-local instructions drifting without central governance.

This contract is additive. It does not replace `Coding_Project_Governance_v1.0`, `GATE_LIFECYCLE_CONTRACT_v1.0`, project profiles, approval envelopes, or stricter project instructions.

## Mandatory runtime banner

For any non-trivial repository, PR, review, docs, orchestration, configuration, release, deployment, or production-data task, the agent must print:

```text
SOURCE INSTRUCTION: <GDRIVE|GIT|GPT_PROJECT|REPO|PACKAGE|MIXED>
EXECUTION MODE: <chat_connector_only|local_agent|repo_ci>
```

When sources conflict, the agent must report the conflict rule and follow the highest-priority active source.

## Chat-only exploration

G0/G1 brainstorming is conversation-local by default. It may produce an
informal intake, options, preflight discussion, and decision candidate without
persisting artifacts, creating a task, or generating an approval token. Label
this state `CHAT_ONLY_PREPARATION` and grant no execution authority.

Formal G0/G1 artifacts, active-provider task creation or claim, and the exact G2
approval command are required only when the user explicitly requests transition
to G2 or asks for a write-capable action.

## Intake Card

Before repository-changing work, the agent must produce an Intake Card:

| Field | Required content |
|---|---|
| Request Type | implementation / review / docs / orchestration / data / visual / other |
| Source Instruction | exact active instruction source and fallback chain |
| Execution Mode | chat_connector_only / local_agent / repo_ci |
| Risk Flags | schema / auth / RLS / finance / security / production / none |
| Required Reads | exact policy and project paths |
| Files READ | exact file paths or connectors to inspect |
| Files WRITE | exact file paths to mutate, or `NONE` |
| Gate Required | G0 / G1 / G2 / G3 / G4 / G5 / G6 |
| Next Action | proceed / blocked / ask approval / prepare patch only |

No repository mutation is allowed until `Files WRITE` is explicit. Writing outside `Files WRITE` is scope drift and requires a new approval request.

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

## Context refresh trigger

The agent must refresh context before any write-capable action and whenever one of these occurs:

- long conversation or unclear current gate;
- user says `continue`, `ok`, `approve`, `go`, `yes`, or equivalent;
- task type, repo, branch, scope, risk, or authority changes;
- protected-base drift is detected; classify the changed files and refresh only
  the evidence required by `SAFE_CONTINUE`, `REVALIDATE`, `REAPPROVE`, or
  `STOP`.
- before PR, merge, deployment, release, credential, production config, migration, or production-data operation.

Refresh output:

```text
SOURCE INSTRUCTION:
Last known gate:
Current request:
Still valid:
Needs reread:
Allowed next action:
```

## Agent-generated approval request

Humans do not invent gate tokens, artifact IDs, scope hashes, branches, file scope, or expiry.

The agent must generate an approval request from current gate evidence and show the full context. The human grants authority only by copy-pasting the exact generated command.

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

Upon completing any gate's exit criteria, the agent must immediately generate the
approval request for the next gate without waiting for the user to ask. This
proactive transition ensures no gate ends in a silent state and the user always
has a clear, actionable next step.

The agent must:

1. Confirm the current gate's exit criteria are fully satisfied and validated.
2. Generate the next gate's entry artifact (execution envelope, delivery record,
   or approval record) using the current gate's evidence.
3. Present the generated approval command in a standalone fenced text block.
4. Wait for the user to execute the command before proceeding to the next gate.

The user retains sole authority to grant or deny the next gate. The agent's
proactive generation is a convenience mechanism, not a delegation of authority.
The agent must not proceed to the next gate until the user executes the approval
command.

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

Unless stricter project rules say otherwise:

- create Draft PR only;
- do not request reviewers automatically;
- do not mark ready for review automatically;
- do not merge or enable auto-merge without G4 authority;
- CI success is evidence only, not authority.
