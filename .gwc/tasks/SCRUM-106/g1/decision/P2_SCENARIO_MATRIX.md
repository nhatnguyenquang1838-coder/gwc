# SCRUM-106 — P2 Scenario and Crash/Recovery Matrix (R2)

- Run: `g1-scrum-106-r2-20260726-2310`
- Current protected base: `c855336dc17f20115e640516107999b08e9d783e`
- Matrix SHA-256: `e5af87d89e2e6bafeb43d2658d54f7b7cebc02e9d6c01f4ab9c4faec24c5d705`
- Contract binding: `BOUND_TO_SCRUM-105_DURABLE_RUNTIME_CONTRACT_V0.1`
- Coverage: **27 scenarios**, **6 crash boundaries**

## Binding status

Logical event names are readable test labels. Durable identity, ordering, actor/gate/outcome, checkpoint, lease/fencing and unknown external-effect semantics are governed by the merged SCRUM-105 contracts.

| Canonical surface | Path |
|---|---|
| Contract/schema | `core/node-architect/DURABLE_RUNTIME_STORE_CONTRACT_v0.1.md` |
| Contract/schema | `schemas/runtime/durable-run.schema.json` |
| Contract/schema | `schemas/runtime/durable-event.schema.json` |
| Contract/schema | `schemas/runtime/durable-checkpoint.schema.json` |
| Contract/schema | `schemas/runtime/pending-action.schema.json` |
| Contract/schema | `schemas/runtime/adapter-contract.schema.json` |
| Contract/schema | `schemas/runtime/storage-migration.schema.json` |

## Supporting-input qualification

- SCRUM-142 graph snapshot is repository-derived and UA-compatible; it is **not** represented as a direct full UA engine run.
- This limitation is a warning only and does not block the K2 contract matrix.

## Node classes

| ID | Title | Effect | Success oracle |
|---|---|---|---|
| `read-only-exact-state` | Read-only exact-state node | external observation only; no mutation | Exact task/repository/SHA/status is observed, persisted, and matches the requested binding. |
| `bounded-external-write` | Bounded external-write node | one authorized external mutation with deterministic readback | One intended external effect is confirmed by live-state readback under the same idempotency key and scope binding. |
| `durable-checkpoint-cas-lease-resume` | Durable checkpoint/CAS/lease/resume node | durable runtime-state mutation only | Checkpoint revision advances exactly once under the active lease/fencing token and resume preserves all bindings. |

## Crash boundaries

| ID | Boundary | Oracle |
|---|---|---|
| `B0` | `before_validation_or_load` | No external or durable state change. |
| `B1` | `after_validation_or_lease_before_intent` | Lease/checkpoint evidence may exist; no node effect. |
| `B2` | `after_intent_before_dispatch_or_commit` | Durable intent may exist; reconcile before retry. |
| `B3` | `after_external_or_store_effect_before_ack` | Effect may have happened; readback is mandatory. |
| `B4` | `after_readback_before_checkpoint_or_human_decision` | No terminal PASS until evidence and checkpoint agree. |
| `B5` | `after_checkpoint_before_terminal_event` | Resume derives terminal result from durable state; no repeat effect. |

## Scenario matrix

| Scenario | Node | Failure class | Boundary | Terminal | Priority | Oracle |
|---|---|---|---|---|---|---|
| `P2-RO-SUCCESS` | `RO` | `SUCCESS` | `B5_AFTER_EVIDENCE_BEFORE_TERMINAL` | `PASS` | P0 | Exact task/repository/SHA/status is observed, persisted, and matches the requested binding. |
| `P2-RO-VALIDATION_FAILURE` | `RO` | `VALIDATION_FAILURE` | `B0_BEFORE_EXECUTION` | `FAILED_VALIDATION` | P0 | No external observation is dispatched and no PASS is emitted. |
| `P2-RO-TIMEOUT_BEFORE_EFFECT` | `RO` | `TIMEOUT_BEFORE_EFFECT` | `B2_BEFORE_DISPATCH` | `RETRYABLE_SUSPENDED` | P0 | No observation result exists; terminal PASS is forbidden. |
| `P2-RO-TIMEOUT_AFTER_EFFECT` | `RO` | `TIMEOUT_AFTER_EFFECT` | `B3_AFTER_REMOTE_READ_BEFORE_EVIDENCE` | `PASS_AFTER_REOBSERVE` | P0 | Result is based on the resumed exact-state observation, not an unevidenced assumption. |
| `P2-RO-DUPLICATE_WORKER` | `RO` | `DUPLICATE_WORKER` | `B1_AFTER_LEASE_ACQUIRE` | `PASS_SINGLE_OWNER` | P0 | Only the active lease holder may publish terminal evidence. |
| `P2-RO-STALE_CHECKPOINT` | `RO` | `STALE_CHECKPOINT` | `B1_ON_RESUME_LOAD` | `STALE_REJECTED` | P0 | No observation is accepted under stale task/SHA/scope/graph revision. |
| `P2-RO-LEASE_EXPIRY` | `RO` | `LEASE_EXPIRY` | `B2_BEFORE_OBSERVATION` | `PASS_AFTER_TAKEOVER` | P0 | Old worker cannot publish after expiry; fresh read determines result. |
| `P2-RO-AMBIGUOUS_POST_STATE` | `RO` | `AMBIGUOUS_POST_STATE` | `B4_AFTER_PARTIAL_READBACK` | `OBSERVABILITY_INCOMPLETE` | P0-HITL | Terminal state remains non-PASS until exact state is observable. |
| `P2-RO-HUMAN_TAKEOVER` | `RO` | `HUMAN_TAKEOVER` | `B4_OPERATOR_ESCALATION` | `HUMAN_RESOLVED_OR_REJECTED` | P0-HITL | Takeover packet contains exact binding, attempts, missing facts and allowed decisions. |
| `P2-BW-SUCCESS` | `BW` | `SUCCESS` | `B5_AFTER_CHECKPOINT_BEFORE_TERMINAL` | `PASS` | P0 | One intended external effect is confirmed by live-state readback under the same idempotency key and scope binding. |
| `P2-BW-VALIDATION_FAILURE` | `BW` | `VALIDATION_FAILURE` | `B0_BEFORE_INTENT` | `FAILED_VALIDATION` | P0 | Mutation call count is zero. |
| `P2-BW-TIMEOUT_BEFORE_EFFECT` | `BW` | `TIMEOUT_BEFORE_EFFECT` | `B2_AFTER_INTENT_BEFORE_DISPATCH` | `RETRYABLE_CONFIRMED_NOT_APPLIED` | P0 | Zero live effect before retry; intent remains durable. |
| `P2-BW-TIMEOUT_AFTER_EFFECT` | `BW` | `TIMEOUT_AFTER_EFFECT` | `B3_AFTER_DISPATCH_BEFORE_RESPONSE` | `PASS_RECONCILED` | P0 | Exactly one live effect; lost response cannot cause duplicate dispatch. |
| `P2-BW-DUPLICATE_WORKER` | `BW` | `DUPLICATE_WORKER` | `B2_CONCURRENT_DISPATCH_ATTEMPT` | `PASS_SINGLE_EFFECT` | P0 | External mutation count is one and stale fencing token writes are zero. |
| `P2-BW-STALE_CHECKPOINT` | `BW` | `STALE_CHECKPOINT` | `B2_BEFORE_INTENT_OR_RETRY` | `STALE_RECONCILE_REQUIRED` | P0 | No new mutation occurs from a stale revision. |
| `P2-BW-LEASE_EXPIRY` | `BW` | `LEASE_EXPIRY` | `B3_IN_FLIGHT_ACTION` | `PASS_AFTER_FENCED_TAKEOVER` | P0 | Fencing rejects old owner checkpoint writes and prevents second external effect. |
| `P2-BW-AMBIGUOUS_POST_STATE` | `BW` | `AMBIGUOUS_POST_STATE` | `B4_INCONCLUSIVE_READBACK` | `AMBIGUOUS_HUMAN_REQUIRED` | P0-HITL | PASS and repeat dispatch are both forbidden while readback is ambiguous. |
| `P2-BW-HUMAN_TAKEOVER` | `BW` | `HUMAN_TAKEOVER` | `B4_OPERATOR_ESCALATION` | `HUMAN_RESOLVED_OR_ABORTED` | P0-HITL | Packet includes intent hash, idempotency key, request/response, readback, lease and checkpoint evidence. |
| `P2-DR-SUCCESS` | `DR` | `SUCCESS` | `B5_AFTER_CHECKPOINT_BEFORE_TERMINAL` | `PASS` | P0 | Checkpoint revision advances exactly once under the active lease/fencing token and resume preserves all bindings. |
| `P2-DR-VALIDATION_FAILURE` | `DR` | `VALIDATION_FAILURE` | `B0_BEFORE_LOAD` | `FAILED_VALIDATION` | P0 | No lease or checkpoint mutation occurs. |
| `P2-DR-TIMEOUT_BEFORE_EFFECT` | `DR` | `TIMEOUT_BEFORE_EFFECT` | `B2_BEFORE_CHECKPOINT_COMMIT` | `RETRYABLE_CONFIRMED_NOT_COMMITTED` | P0 | Checkpoint revision advances zero times. |
| `P2-DR-TIMEOUT_AFTER_EFFECT` | `DR` | `TIMEOUT_AFTER_EFFECT` | `B3_AFTER_COMMIT_BEFORE_ACK` | `COMMIT_RECONCILED` | P0 | Checkpoint revision advances exactly once despite lost acknowledgment. |
| `P2-DR-DUPLICATE_WORKER` | `DR` | `DUPLICATE_WORKER` | `B2_CONCURRENT_CAS` | `PASS_SINGLE_WRITER` | P0 | One successful CAS; no two owners share a valid fencing token. |
| `P2-DR-STALE_CHECKPOINT` | `DR` | `STALE_CHECKPOINT` | `B1_ON_LOAD` | `STALE_REJECTED` | P0 | Stale revision never overwrites current state. |
| `P2-DR-LEASE_EXPIRY` | `DR` | `LEASE_EXPIRY` | `B2_DURING_NODE` | `RESUMED_NEW_FENCE` | P0 | Every post-takeover write carries the new token and old-token rowcount is zero. |
| `P2-DR-AMBIGUOUS_POST_STATE` | `DR` | `AMBIGUOUS_POST_STATE` | `B4_STORE_UNAVAILABLE_ON_READBACK` | `STORE_STATE_UNKNOWN` | P0-HITL | No false next-node advancement during store ambiguity. |
| `P2-DR-HUMAN_TAKEOVER` | `DR` | `HUMAN_TAKEOVER` | `B4_OPERATOR_ESCALATION` | `HUMAN_TAKEOVER_RESUMED` | P0-HITL | Human cannot silently overwrite active lease or skip pending-action readback. |

## Global invariants

- CAS expected revision is mandatory for every checkpoint advance.
- Only the active lease holder with current fencing token may advance state.
- Unknown external outcomes are reconciled before retry.
- Checkpoint is persisted before suspend, approval wait or takeover.
- PASS is impossible when live state, checkpoint and expected node exit disagree.
- Idempotency constrains retries but does not replace readback.
- Human takeover is an audited state transition, not a hidden bypass.
- SQLite and PostgreSQL adapters must satisfy the same observable contract.

## Acceptance gates

- **K2-AC-01** — Exactly 27 base scenarios exist: 3 node classes × 9 required classes.
- **K2-AC-02** — Every scenario defines injection boundary, ordered logical events, terminal status, retry policy, forbidden behavior, evidence, and deterministic oracle.
- **K2-AC-03** — No scenario permits false PASS, stale-owner advancement, or blind retry after unknown write result.
- **K2-AC-04** — Bounded external-write scenarios prove one observable effect using durable intent, unique idempotency key, readback, CAS and fencing.
- **K2-AC-05** — Human takeover scenarios produce a complete audited takeover packet and bounded decisions.
- **K2-AC-06** — Every logical event and evidence oracle is mapped to the merged SCRUM-105 durable run/event/checkpoint/pending-action contracts before implementation.
- **K2-AC-07** — SQLite and PostgreSQL/Supabase adapter suites run the same behavioral matrix, with adapter-specific contention and RLS checks.
- **K2-AC-08** — The crash harness can inject at B0-B5 and verify store/live-state outcomes after process restart.
