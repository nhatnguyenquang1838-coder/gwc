# GWC FastLane Bootstrap Runbook

## Purpose

This runbook tells a ChatGPT-style agent how to use `GWC_FASTLANE_BOOTSTRAP_WORKFLOW_v0.1` to deliver a temporary, bounded GWC governance update through a guarded branch and Draft PR.

It is intended for GWC self-upgrade work only.

## Runtime banner

Start with:

```text
SOURCE INSTRUCTION: REPO
EXECUTION MODE: chat_connector_only
```

## Step 1 — Boot

Read protected-base governance before any write-capable connector call:

1. `AGENTS.md`
2. `core/Coding_Project_Governance_v1.0.md`
3. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
4. `core/Agent_Operating_Runtime_Contract_v1.0.md`
5. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
6. `governance/instruction-source-registry.yaml`
7. `projects/gwc/project-profile.yaml`
8. `projects/gwc/project-instructions.md`
9. `projects/gwc/project-extension.md`
10. `agents/chatgpt-agent/agent-instructions.md`

## Step 2 — Intake

Produce an Intake Card with:

- request type;
- source instruction;
- execution mode;
- risk flags;
- files read;
- files write;
- required gate;
- next action.

## Step 3 — Conversation-local G0/G1

For FastLane only, ChatGPT may capture G0/G1 as a conversation-local packet.

The agent must not call this a normal formal G1 validator PASS unless trusted validator evidence exists.

## Step 4 — Generate FastLane envelope

Create a FastLane envelope that conforms to:

```text
schemas/fastlane/fastlane-envelope.schema.json
```

The envelope must bind:

- repository;
- base SHA;
- working branch;
- connector route;
- files read;
- files write;
- authorized actions;
- excluded actions;
- approval expiry;
- scope hash.

## Step 5 — Request exact G2 approval

Show exactly one command:

```text
APPROVE G2 <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Do not proceed on plain `ok`, `approve`, `continue`, `go`, or equivalent.

## Step 6 — Execute after G2 approval

After exact approval:

1. verify `main` still matches the envelope base SHA;
2. create the guarded branch;
3. write only scoped files;
4. read back branch diff;
5. create or update a Draft PR.

## Step 7 — Draft PR body

The Draft PR must include:

```text
Workflow:
Approval:
Base SHA:
Head SHA:
Files changed:
Validation performed:
Validation skipped:
Evidence:
Limitations:
Excluded actions:
```

## Step 8 — Stop before merge

FastLane stops at Draft PR delivery or G3 review preparation.

Merge requires separate G4 approval for the exact PR and head SHA.

## Failure handling

Stop and regenerate scope or approval when:

- `main` drift is detected;
- a new file path is needed;
- validation scope changes;
- architecture/security/production impact appears;
- approval expires;
- connector rejects the write;
- branch or PR head changes unexpectedly.

## Jira and TC / DS MCP

Jira and TC / DS MCP updates are optional audit projection only.

Failure to sync Jira or TC does not invalidate Git delivery evidence, but must be reported honestly.

## Sunset

When `REVAMP_UPGRADE_GWC` is merged and validated, this workflow must be removed or deprecated.
