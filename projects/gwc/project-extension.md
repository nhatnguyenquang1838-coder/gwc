# GWC Project Extension

## Status

- Extends: `projects/gwc/project-profile.yaml`
- Scope: `nhatnguyenquang1838-coder/gwc`
- Runtime: DWC
- Authority: non-authoritative relative to system, platform, developer, and
  canonical core policy

## Automatic gate policy

When higher-priority DWC runtime instructions are active for this project:

- G0 intake and G1 read-only inspection are automatic.
- G2 execution is automatic for bounded non-risk changes.
- G3 Draft PR creation is automatic after validation for bounded non-risk
  changes.
- Human direction is required for financial, architecture, security-boundary,
  production configuration, credential, secret, production-data, destructive,
  irreversible, or broad-blast-radius changes.
- G4 merge, G5 deploy, and G6 production operations always remain human gates.

## Global G0/G1 operational runbook

All GWC agents follow `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md` for the step-by-step execution of G0_CONTEXT and G1_ALIGNMENT. This project extension may tighten that runbook but must not weaken its proposal obligation, local `/mnt` validation path, connector retry behavior, approval boundaries, or G4-G6 HITL requirements.

## Repository safety

- Use one dedicated allowed-prefix branch per Jira task.
- Never write directly to `main`.
- Verify repository identity and protected-base SHA before writes.
- Re-read existing files before updating them.
- Keep writes within the active task scope.
- Open a Draft PR and report current head SHA and CI state.
- Never treat CI success as merge or deployment authority.

## Jira task traceability

Every new modifying task must have exactly one Jira issue in project `SCRUM`.
Atlassian MCP records the repository, base branch, working branch, PR, validation
outcome, and final task state. Jira task status does not grant G0-G6 authority.
Existing DS Admin and Rental Home task records remain unchanged.

For AI or automated agent execution, the existing Jira fields `AI Agent` and
`Claimed At` are mandatory intake evidence and must be read back before any
write-capable repository, PR, Jira transition, Slack projection, or gate action.
This is an agent-only requirement; human-executed work is not blocked by empty
agent claim fields.

## Hotfix and Rescue Mode Support

This project acknowledges the existence of HOTFIX and RESCUE mode policies
defined in `core/HOTFIX_AND_RESCUE_MODE_v1.0.md`. These modes provide bounded
bypass capabilities for emergency or time-critical fixes while maintaining
core safety guarantees:

### HOTFIX MODE
- Light validation (skips some optional checks)
- Standard documentation required
- Bounded to explicitly stated scope
- Agent-only task claim intake still required before any write-capable action
- Draft PR only, no merge authority

### RESCUE MODE
- Minimal validation (best-effort testing only)
- Post-facto audit trail required
- Agent-only task claim intake still required before any write-capable action when Jira is reachable
- Still no production data access or main branch writes
- Draft PR only, no merge authority

**Activation requires explicit user command:**
```text
ACTIVATE HOTFIX <scope-hash-prefix> [description]
ACTIVATE RESCUE <scope-hash-prefix> [description]
TRULY EMERGENCY OVERRIDE [brief description]
```

All activation commands must be in standalone fenced text blocks. The user
acknowledges that bypassing standard gates requires post-facto review and
retrospective task claiming through the active Jira workflow when applicable.
Retrospective claiming must never backdate `Claimed At`.

**No mode overrides:**
- Explicit GWC boot unless the user says `NO GWC`, `Không GWC`, `loại bỏ GWC`, or `ignored GWC`
- Agent-only task claim intake before write-capable action
- Production data reads/writes (G6)
- Credential/secret rotation
- Merge authority (G4 requires human approval)
- Deploy authority (G5 requires human approval)

## Node runtime mode invariant

All executable Node Architect routes enforce `MODE_DOES_NOT_BYPASS_NODE_RUNTIME`.
Normal, fastlane, e2e, hotfix, and rescue modes may alter validation depth,
batching, or continuation strategy, but they must still complete GWC boot, agent
claim intake, separate gate-authority validation, route resolution, node
instruction validation, canonical evidence/log recording, and next-route
resolution. Missing instruction, evidence, logs, next route, or an authority-
escalating instruction fails closed before implementation.

Jira, Slack, and Notion remain projection-only. Node instructions and route
decisions never grant G2, G3, G4, G5, or G6 authority.

## Governance hardening (SCRUM-268)

- The `g4-receipt-required` GitHub check is the repository-side enforcement
  surface for G4. It must fail until a trusted `gwc:g4-authority-receipt`
  exists. Enabling it as a required branch-protection check is a manual
  repository-admin follow-up; the workflow itself must never treat a missing
  receipt as success.
- Gate artifacts under `.gwc/tasks/<task-id>/` are evidence projections and
  must not silently invalidate the implementation binding. The deterministic
  ordering is: finish implementation and validation at the approved base/head;
  calculate and approve the implementation scope; write gate artifacts only as
  task evidence; if an artifact commit changes the bound head, invalidate the
  prior approval and rebind before any PR authority action. No stale token may
  be reused.
- `calculate_gate_scope_identity` exposes `scope_hash` only when
  `outcome: READY`; a `BLOCKED` result has `scope_hash: null` and is never
  eligible for an approval command.
- Jira is non-attributive unless authenticated per-agent Atlassian identities
  are provisioned. The selected target is one service account per agent,
  requiring manual Atlassian-admin provisioning and connector migration. Until
  then, GitHub identity and signed repository evidence are authoritative for
  agent attribution; Jira fields/comments are projections only.
