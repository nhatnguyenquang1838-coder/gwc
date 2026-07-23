# Runtime Kernel v0.1

## Status

- Kernel ID: `RUNTIME_KERNEL`
- Version: `0.1`
- Scope: `REVAMP_UPGRADE_GWC`
- Introduced by: `REVAMP-GWC-009`
- Lifecycle: additive node-architect runtime contract

## Purpose

The Runtime Kernel defines the small set of invariants that every future GWC runtime node, node pack, transition envelope, and checkpoint/resume implementation must obey before the node catalog is expanded.

It sits above individual node content and below the existing GWC gate lifecycle. It does not replace G0-G6, `CHECKPOINT_RESUME_RULE`, `KIRO_STRICT_CODING_STATE_RULE`, or Draft PR delivery rules.

## Research basis

Context7 durable-execution research for Temporal-style systems was used as reference material. The selected patterns are:

1. event history as the replay source;
2. idempotency keys for side-effect activities;
3. explicit command-to-event boundaries;
4. checkpoint/resume after crash or restart;
5. version pinning for active runs.

The reference material is non-authoritative. Protected-base GWC governance remains the authority.

## Core principle

```text
Runtime progress = kernel invariants + canonical checkpoint + event history + current repo evidence.
External projection = audit or resume hint only.
```

## Global invariants

| Invariant | Requirement |
|---|---|
| `authority_boundary` | Any action that writes, marks ready, merges, deploys, or touches production must bind to the correct GWC gate and exact approval boundary. |
| `event_history` | Runtime actions must emit durable events before state is treated as replayable. |
| `idempotency_key` | Side-effect nodes must derive or receive a stable idempotency key before external mutation. |
| `checkpoint_before_suspend` | Any wait, human approval, connector unavailable state, or handoff must checkpoint the current node, next node, and exact next action. |
| `readback_after_side_effect` | Any side effect must be followed by readback evidence before PASS or transition. |
| `exact_evidence_binding` | PR, branch, commit, CI, package-export, and validation evidence must bind to exact SHA or exact artifact identifier. |
| `version_pin` | Active runs must declare the kernel version and node pack version they were started with. |
| `projection_is_not_authority` | Jira, TC, DS MCP, Notion, comments, labels, dashboards, and generated `.governance/` exports are not canonical authority. |
| `no_blind_retry` | Retry is forbidden unless the prior event/checkpoint proves the previous side effect is safe to repeat or already reconciled. |
| `catalog_expansion_gate` | New node catalog expansion must wait until kernel, schemas, validator, and representative node packs pass. |
| `human_bypass_is_operational_only` | HUMAN BYPASS may hand one exact operational step to a human; it never weakens the minimum gate or protected-action boundary. |
| `human_bypass_readback_before_resume` | A bypassed step remains suspended until append-only audit, deterministic readback, and checkpoint-after evidence are persisted. |

## Runtime state lanes

```mermaid
flowchart LR
  A[Kernel invariants] --> B[Runtime event history]
  B --> C[Checkpoint]
  C --> D[Transition envelope]
  D --> E[Node pack]
  E --> F[Future catalog]
```

| Lane | Canonical? | Description |
|---|---:|---|
| `kernel` | Yes | Global runtime invariant set. |
| `event_history` | Yes | Append-only evidence of runtime commands and outcomes. |
| `checkpoint` | Yes | Current resume point and exact next action. |
| `transition_envelope` | Yes | One bounded movement from a node to a next node. |
| `node_pack` | Yes when validated | Versioned bundle of nodes, schemas, and allowed transitions. |
| `external_projection` | No | Audit/dashboard/search/help surface only. |

## HUMAN BYPASS lane

```text
blocked eligible operational step
→ checkpoint_before
→ HUMAN_BYPASS request
→ human exact action
→ human_bypass_* runtime events
→ deterministic readback
→ checkpoint_after
→ resume
```

The canonical record is defined by `core/HUMAN_BYPASS_CONTRACT_v1.0.md` and `schemas/human-bypass.schema.json`. A bypass request is invalid after expiry or any task, gate, node, branch, base SHA, head SHA, action, or scope drift. Protected-branch write, validation/CI skipping, merge, deploy, production, secret, credential, migration, destructive action, force-push, branch deletion, history rewrite, and PR base change are never bypass-eligible.

## Gate mapping

| Runtime concern | Required GWC gate behavior |
|---|---|
| Read-only context load | G0/G1 |
| Scope selection and option decision | G1 |
| Repository write | G2 exact approval |
| Draft PR delivery and exact-head review | G3 |
| Merge | G4 exact approval for current PR head SHA |
| Deployment/release | G5 exact approval if ever introduced |
| Production data/config/secrets/migration | G6 exact approval if ever introduced |

## Node expansion rule

The 81-node catalog or any large lazy-loaded node library must not be implemented until all of these are true:

1. `RUNTIME_KERNEL_v0.1.md` exists and is packaged;
2. runtime kernel, runtime event, transition envelope, and node pack schemas exist;
3. `validate_runtime_kernel_contract.py` returns `PASS`;
4. representative read-only, side-effect, and suspend/resume node packs are defined in a later scoped PR;
5. failure simulation proves no duplicate side effect, stale approval use, or false PASS.

## Compatibility

This kernel is additive. It extends existing REVAMP node-architect contracts and does not grant any protected-branch write, merge, auto-merge, deploy, release, production configuration, credential, secret, migration, production-data, force-push, branch-deletion, or PR-base-change authority.
