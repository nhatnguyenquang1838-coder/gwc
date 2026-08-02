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
- Agent-only claim intake before write-capable action
- Production data reads/writes (G6)
- Credential/secret rotation
- Merge authority (G4 requires human approval)
- Deploy authority (G5 requires human approval)
