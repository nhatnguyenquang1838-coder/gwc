# REVAMP_UPGRADE_GWC Runbook

## Purpose

This runbook explains how ChatGPT-style agents should use the merged FastLane bootstrap workflow to deliver the first `REVAMP_UPGRADE_GWC` foundation PR.

## Runtime banner

```text
SOURCE INSTRUCTION: REPO
EXECUTION MODE: chat_connector_only
```

## Step 1 — Boot

Read protected-base governance and the merged FastLane workflow before any write-capable connector call:

1. `AGENTS.md`
2. `core/Coding_Project_Governance_v1.0.md`
3. `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
4. `core/Agent_Operating_Runtime_Contract_v1.0.md`
5. `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
6. `projects/gwc/project-profile.yaml`
7. `agents/chatgpt-agent/agent-instructions.md`
8. `core/workflows/GWC_FASTLANE_BOOTSTRAP_WORKFLOW_v0.1.md`
9. `docs/runbooks/GWC_FASTLANE_BOOTSTRAP_RUNBOOK.md`
10. `schemas/fastlane/fastlane-envelope.schema.json`

## Step 2 — Confirm FastLane activation

The user must explicitly request use of the merged FastLane workflow for GWC revamp work.

The activation phrase is not G2 approval. The agent must generate an exact G2 command.

## Step 3 — Conversation-local G0/G1

For this temporary route, ChatGPT may prepare:

- request type;
- selected workflow;
- task ID;
- base SHA;
- Files READ;
- Files WRITE;
- authorized actions;
- excluded actions;
- risk class;
- acceptance criteria;
- non-goals.

Do not claim normal formal `G1_ALIGNMENT: PASS` unless validator evidence exists.

## Step 4 — Generate revamp envelope

Generate an envelope matching:

```text
schemas/node-architect/revamp-upgrade-gwc-envelope.schema.json
```

The envelope must bind:

- `REVAMP-GWC-001`;
- repo `nhatnguyenquang1838-coder/gwc`;
- exact protected base SHA;
- dedicated working branch;
- connector route;
- Files READ and Files WRITE;
- external audit projection as non-blocking;
- prohibited actions.

## Step 5 — Ask exact G2 approval

Show a command in this form:

```text
APPROVE G2 <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Do not proceed on plain `ok`, `approve`, `continue`, `go`, or equivalent.

## Step 6 — Execute after G2 approval

After exact approval:

1. verify `main` still equals the envelope base SHA;
2. create the guarded branch;
3. write only the approved files;
4. read back diff from base to branch;
5. create a Draft PR;
6. report validation performed, validation skipped, evidence, and limitations.

## Step 7 — G3/G4

G3 is Draft PR delivery and evidence assembly only.

G4 merge requires separate exact human approval for the current PR head SHA.

## Audit projection

Jira, TC, DS MCP, Git comments, Git labels, or dashboards are optional audit projections. They are non-blocking by default and must not be treated as gate authority.

## Stop conditions

Stop and regenerate approval when:

- base SHA changes materially;
- Files WRITE needs expansion;
- a prohibited action becomes necessary;
- validation requires unapproved files;
- another actor changes the branch;
- connector rejects the action;
- approval expires;
- deploy/release/production scope appears.

## Follow-up

After this foundation PR is merged and validated, the next PR should either extend the node-architect model or deprecate FastLane when the replacement workflow is ready.
