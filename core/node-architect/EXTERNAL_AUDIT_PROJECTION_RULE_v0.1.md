# External Audit Projection Rule v0.1

## Status

- Rule ID: `EXTERNAL_AUDIT_PROJECTION_RULE`
- Version: `0.1`
- Applies to: `REVAMP_UPGRADE_GWC`
- Scope: Jira, TC, DS MCP, Git comments, Git labels, dashboard mirrors

## Purpose

This rule prevents external workflow systems from accidentally becoming coding-gate authority during GWC revamp work.

External systems may show, comment on, mirror, or summarize the current state. They do not decide whether G0, G1, G2, G3, G4, G5, or G6 has passed.

## Core rule

```text
External audit projection is non-blocking unless an approved GWC gate explicitly declares it blocking.
```

## Source-of-truth split

| Domain | Canonical source | External projection role |
|---|---|---|
| Coding gate state | GWC gate evidence and task checkpoint | Mirror only |
| Branch and PR state | GitHub branch, PR, head SHA, diff, CI | Link or label only |
| Review readiness | G3 delivery evidence | Optional comment/status |
| Merge authority | G4 exact approval | No authority |
| Deployment authority | G5 exact approval when manual action exists | No authority |
| Production authority | G6 exact approval | No authority |

## Projection states

```text
AUDIT_NOT_REQUIRED
AUDIT_PENDING
AUDIT_SUBMITTED
AUDIT_VERIFIED
AUDIT_STALE
AUDIT_FAILED
AUDIT_SKIPPED
```

## Allowed projections

- Jira comment with gate summary.
- Jira status transition when a connector and actor policy allow it.
- TC / DS MCP mirror snapshot.
- GitHub PR comment or label.
- Dashboard freshness indicator.

## Forbidden interpretations

External audit projection MUST NOT be interpreted as:

- G2 write approval;
- G3 review pass;
- G4 merge approval;
- G5 deploy approval;
- G6 production approval;
- proof that CI passed;
- proof that current head SHA is still valid.

## Failure behavior

If projection fails:

| Failure | Coding gate impact | Required report |
|---|---|---|
| Jira unavailable | Non-blocking | `AUDIT_FAILED` with reason |
| TC unavailable | Non-blocking | `AUDIT_FAILED` with reason |
| Git label/comment unavailable | Non-blocking unless explicitly required | report limitation |
| Actor identity mismatch | Non-blocking by default | record actor mismatch |
| Projection stale | Non-blocking by default | record freshness timestamp |

## Actor identity

When external systems have audit identity requirements, the projection must record:

- requested actor;
- executing connector or client;
- readback actor when available;
- timestamp;
- whether the action was blocking.

A projection performed by the wrong actor must not be hidden. It should be marked `AUDIT_FAILED` or `AUDIT_STALE`, not converted into gate failure unless the gate explicitly required that actor readback.

## Minimal projection packet

```yaml
schema_version: "0.1"
projection_type: external_audit
task_id: REVAMP-GWC-001
canonical_gate: G3_PR
canonical_status: PASS
blocking: false
targets:
  jira:
    enabled: true
    status: AUDIT_PENDING
  tc_ds_mcp:
    enabled: true
    status: AUDIT_PENDING
  git:
    enabled: true
    status: AUDIT_VERIFIED
```

## Compatibility

This rule is additive. It does not remove any existing GWC validator, schema, gate artifact, or CI requirement.
