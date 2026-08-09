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
- G4 merge authority is human by default. A canonical route-specific policy may
  supply bounded standing G4 authority for an exact action when that policy is
  active and all of its bindings validate. For
  `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`, a valid exact-head standing G4 may
  authorize only the bounded `auto/* -> pre-prod` child merge. Human G4 remains
  mandatory for every `pre-prod -> main` promotion/merge.
- Manual G5 deploy/redeploy/release/runtime actions and all applicable G6
  production operations remain separate human-authority boundaries.

## Global G0/G1 operational runbook

All GWC agents follow `core/runbooks/GATE_G0_G1_OPERATIONAL_RUNBOOK_v1.0.md` for the step-by-step execution of G0_CONTEXT and G1_ALIGNMENT. This project extension may tighten that runbook but must not weaken its proposal obligation, local `/mnt` validation path, connector retry behavior, approval boundaries, or applicable human-authority requirements.

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
- Draft PR only; this mode itself grants no merge authority

### RESCUE MODE
- Minimal validation (best-effort testing only)
- Post-facto audit trail required
- Agent-only task claim intake still required before any write-capable action when Jira is reachable
- Still no production data access or main branch writes
- Draft PR only; this mode itself grants no merge authority

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
- Merge authority resolution: human is the default G4 authority source; a
  canonical route-specific standing G4 is valid only for the exact action it
  explicitly authorizes, and never for autonomous merge/promotion to `main`
- Manual deploy authority (G5 requires human approval)

## Route-specific authority precedence

Route resolution happens before generic workflow authority wording is applied.
For an active canonical route, route-specific authority determines the authority
source for the exact gate/action; generic E2E, project-extension, or agent text
supplies default behavior only and must not replace a valid route-specific
decision.

For `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`:

```text
G0/G1/G2/G3 mechanics
-> resolve canonical route-specific G4 authority
-> valid exact-head standing G4: auto/* -> pre-prod merge allowed
-> exact merge-SHA G5 readback
-> pre-prod -> main: Human G4 required
```

A missing, stale, or invalid standing autonomous authority fails closed under the
autonomous policy. It must not be repaired by silently switching the same child
action to generic Human G4 semantics.

## Node runtime mode invariant

All executable Node Architect routes enforce `MODE_DOES_NOT_BYPASS_NODE_RUNTIME`.
Normal, fastlane, e2e, hotfix, and rescue modes may alter validation depth,
batching, or continuation strategy, but they must still complete GWC boot, agent
claim intake, separate gate-authority validation, route resolution, node
instruction validation, canonical evidence/log recording, and next-route
resolution. Missing instruction, evidence, logs, next route, or an authority-
escalating instruction fails closed before implementation.

Jira, Slack, and Notion remain projection-only. Node instructions and route
decisions never grant G2, G3, G4, G5, or G6 authority; authority comes from the
validated gate/route authority source.

## Governance hardening (SCRUM-268)

- The `g4-receipt-required` GitHub check is the repository-side enforcement
  surface for G4. It must fail until the applicable trusted G4 authority receipt
  exists. For generic routes this is a human-derived receipt. For an active
  canonical autonomous pre-prod route it may be the validated route-specific
  exact-head standing G4 receipt. A receipt for `auto/* -> pre-prod` never
  authorizes `pre-prod -> main`.
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