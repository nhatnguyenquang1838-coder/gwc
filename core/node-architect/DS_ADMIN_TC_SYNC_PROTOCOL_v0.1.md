# DS Admin / TC Sync Protocol v0.1

## Status

- Protocol ID: `DS_ADMIN_TC_SYNC_PROTOCOL`
- Version: `0.1`
- Scope: `REVAMP_UPGRADE_GWC`
- Introduced by: `REVAMP-GWC-004`
- Lifecycle: additive node-architect projection protocol

## Purpose

This protocol defines how GWC work may be mirrored into DS Admin and TC without
turning either system into coding-gate authority.

It supports visibility, dashboard freshness, resume hints, and traceability
while preserving the GWC authority chain.

## Core rule

```text
DS Admin / TC sync is an external audit projection.
It is never source-of-truth for G0, G1, G2, G3, G4, G5, or G6 unless a future
approved GWC gate explicitly changes that boundary.
```

## Authority split

| Domain | Canonical source | DS Admin / TC role |
|---|---|---|
| Gate state | GWC checkpoint and gate evidence | Mirror only |
| Approval authority | Exact GWC approval command | No authority |
| Branch / PR / CI | GitHub branch, PR, head SHA, CI | Link and display only |
| Resume | Canonical checkpoint + repo evidence | Hint only |
| Merge | G4 exact approval + GitHub readback | No authority |
| Deploy / production | G5/G6 exact approvals where applicable | No authority |

## Sync packet requirements

Every DS Admin / TC sync packet MUST include:

| Field | Meaning |
|---|---|
| `schema_version` | Protocol schema version |
| `protocol_id` | `DS_ADMIN_TC_SYNC_PROTOCOL` |
| `task_id` | GWC task or revamp work item |
| `checkpoint_id` | Canonical checkpoint identifier |
| `source_of_truth` | MUST be `canonical_checkpoint` |
| `gate` | Current canonical gate and status |
| `repository` | Repository, base branch, base SHA |
| `git_delivery` | Branch, PR, head SHA, CI status when available |
| `targets` | DS Admin / TC target projection records |
| `authority` | Explicit non-authority flags |
| `readback` | Optional target confirmation and freshness |

## Target statuses

```text
SYNC_NOT_REQUIRED
SYNC_PENDING
SYNC_SUBMITTED
SYNC_VERIFIED
SYNC_STALE
SYNC_FAILED
SYNC_SKIPPED
```

## Blocking behavior

DS Admin / TC sync is non-blocking by default.

A sync target may only be `blocking=true` when the current gate evidence contains
an explicit `blocking_sync_declared=true` field. Without that declaration, a
blocking target is invalid.

## Valid operations

- Render a deterministic projection packet from a canonical checkpoint.
- Submit a DS Admin task-state mirror.
- Submit a TC dashboard snapshot.
- Read back target freshness and status.
- Report stale or failed projection without failing the coding gate by default.

## Invalid operations

A DS Admin / TC sync packet MUST NOT:

- grant G2 write authority;
- mark G3 PASS without PR/head/CI evidence;
- grant G4 merge authority;
- mark CI as passed without GitHub evidence;
- replace a missing checkpoint;
- change the PR base;
- deploy, release, migrate, or touch production data;
- contain credentials, secrets, or private production data.

## Failure behavior

| Failure | Coding gate impact | Required reporting |
|---|---|---|
| DS Admin unavailable | Non-blocking by default | `SYNC_FAILED` with reason |
| TC unavailable | Non-blocking by default | `SYNC_FAILED` with reason |
| Readback unavailable | Non-blocking by default | `SYNC_STALE` or limitation |
| Actor mismatch | Non-blocking by default | record requested/executing/readback actor |
| Blocking target without gate declaration | Invalid packet | validator failure |

## Minimal projection packet

```yaml
schema_version: "0.1"
protocol_id: DS_ADMIN_TC_SYNC_PROTOCOL
task_id: REVAMP-GWC-004
checkpoint_id: chk_revamp_gwc_004
source_of_truth: canonical_checkpoint
gate:
  current: G3_PR
  status: PASS
  blocking_sync_declared: false
authority:
  external_system_authority: false
  requires_g4_for_merge: true
targets:
  - target_type: ds_admin
    enabled: true
    blocking: false
    status: SYNC_PENDING
  - target_type: tc
    enabled: true
    blocking: false
    status: SYNC_PENDING
```

## Compatibility

This protocol extends `EXTERNAL_AUDIT_PROJECTION_RULE` and
`CHECKPOINT_RESUME_RULE`. It does not remove existing GWC validators, gate
lifecycle rules, approval boundaries, or Git delivery evidence requirements.
