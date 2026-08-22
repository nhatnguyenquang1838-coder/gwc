# ChatGPT Agent Instructions — Composed Entrypoint

This is the mandatory ChatGPT instruction entrypoint for GWC.

## Load order

Always load and follow:

1. parent/root `AGENTS.md` and higher-priority GWC/project instructions;
2. `agents/chatgpt-agent/gwc-governed-base.md` — the complete GWC ChatGPT base instruction set;
3. additional role overlays that apply to the active task.

## Slack Controller mode

When ChatGPT acts as Controller for a Slack-mediated Executor run, it MUST additionally load and follow, in order:

1. `agents/shared/slack-controller-executor-protocol.md`;
2. `agents/chatgpt-agent/slack-controller-mvp.md`.

The Slack Controller overlay is mandatory for that mode, not optional reference material.

It owns Controller decomposition, selected-option Executor Contract compilation, milestone/report timing, RootCard state, `CONTINUE | WAIT_CONTROLLER | TERMINAL` boundaries, in-session 60-second incremental Slack polling, report review, and bounded INTERCEPT decisions.

When GWC is active, do not delegate write-capable execution before valid G2 authority exists. Build the Executor-facing contract from canonical G0 context, the G1 selected option only, exact G2 authority, and exact current repository evidence. Do not forward rejected alternatives or brainstorming noise to the Executor.

For Slack Controller monitoring, the 60-second cadence in `slack-controller-mvp.md` overrides any generic longer ChatGPT thread-sleep cadence only for that monitoring loop. It does not weaken gate or authority rules.

## Autonomous TaskController mode

When ChatGPT is the autonomous agent for an autonomous-to-pre-prod run, it starts as **TaskController** and MUST additionally load `agents/autonomous-agent/agent-instructions.md` and `skills/task-controller/SKILL.md`. The TaskController delegates bounded implementation through the existing Slack Controller–Executor protocol and `skills/executor/SKILL.md`; it does not replace Slack with a parallel protocol and Slack remains communication/projection only.

After exact-head CI and independent G3, route to `G4_PREPROD_AUDIT_TRIGGER` and invoke a separate `agent-audit` with `skills/audit-guardrail/SKILL.md`. The audit receipt is read-only evidence with `merge_authority=false`; only the separately trusted standing G4 evaluator may make the pre-prod merge decision.
## Materialized governance contract surface

This composed entrypoint is an additive
runtime overlay on the parent `AGENTS.md`; the parent file remains canonical. Do not downgrade a capable ChatGPT agent when the repo, connector evidence, and isolated validation capability are present.

Connector fallback order is GitHub, then DWC, then DW1. Do not require onboarding every declared connector before continuing; use the first verified connector that can supply the required evidence and legal write path.

Mandatory boot sources include `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md`. Connector-only execution must first Pin and re-verify the protected-base SHA, then Fetch the required gate artifacts, schemas, templates, validators into `/mnt/data/gwc_sessions/<session-id>/`. Repair and retry remediable failures before blocking. Block only when exact validator evidence unavailable after artifact recovery.

Validator availability does not determine execution mode, even if an isolated filesystem and
  command runner can validate fetched artifacts. Persisting those artifacts to the repository remains a G2 write.

Gate transition continuation artifacts:

- G1 PASS | G2 execution envelope plus approval request
- G2 PASS | G3 delivery record
- G3 PASS | G4 merge approval request
- G4 PASS | G5 deployment approval request
- G5 PASS | G6 production approval request

Hard-stop boundaries remain: protected-branch write, merge, deployment, production-data operation, scope drift, expired approval, connector hard denial.

For G5, do not infer a manual deploy/reload from the gate name. G5 status verification starts only after a merge commit exists, uses event=push and head_sha=<merge_sha>, and reports CONNECTOR_OBSERVABILITY_INCOMPLETE when exact post-merge lookup cannot prove the target SHA. For production operation scope, generate G6 only when applicable; otherwise record `not_applicable`.

This transition is not merge approval. Ready-for-review is G3 metadata completion only. late reconciliation must be disclosed as late. Status reports, blockers, evidence summaries, recommendations, and next actions should be written primarily in Vietnamese while preserving technical terms.

Do not copy full executable approval commands into connector payloads. For active CI polling, sleep the current thread for exactly two minutes. Do not create a scheduler task or automation as a substitute for the active wait-and-recheck loop.

G4/G5 GitHub evidence flow:

- APPROVE G4 <approval_id> <scope_hash_16> <expires_at_utc>
- gwc:g4-authority-receipt
- pull_request.closed
- gwc:g4-merge-proof
- gwc:g5-status
- GitHub Actions artifact
- projection_only
- recursive evidence PR

The evidence workflow must not merge the PR. G5 status verification starts only after a merge commit exists; a projection_only or recursive evidence PR never satisfies G5.

G4 trusted receipt handling: CONNECTOR_OBSERVABILITY_LIMITED must not block when the trusted receipt exists but issue_comment` workflow-run listing is unavailable. If the receipt is missing or mismatched, fail closed with G4_RECEIPT_MISSING. Validate approval ID, approved head SHA, scope hash, expiry, source comment, and trusted GitHub Actions bot identity.

Lane integrity obligations: LANE ASSERTION, LANE_ASSERTION_MISSING, LANE_DRIFT_DETECTED, FOREIGN DIRTY STATE, FOREIGN_DIRTY_STATE_DETECTED, gwc:g4-authority-receipt, issue_comment, G4_RECEIPT_MISSING, APPROVE G5 RECOVERY, RECOVERY_EVIDENCE_UNBOUND, source_digest, SHA_MISMATCH.

## Conflict rule

If this composition entrypoint or a role overlay conflicts with parent/root governance or higher-priority instructions, follow the higher-priority instruction. Role overlays may specialize behavior and cadence but must not grant authority.
