# Canonical-81 Shadow Qualification Plan v1.0

## Objective

Prove that the canonical baseline remains exactly 81 node IDs and that every baseline node is safely reachable through the Node Architect shadow runtime without conflating shadow enablement with authoritative readiness.

## Qualification levels

The W1 E0-E5 ladder remains authoritative for executability evidence:

- E0 catalogued
- E1 instruction-ready
- E2 adapter-bound
- E3 route-bound
- E4 replay-proven
- E5 observed

W6 may mark a node `shadow_enabled=true` when adapter binding, route binding, and deterministic replay are proven. `authoritative_candidate` is tracked separately and is false for descriptor-only semantics.

## E0 replay matrix

E0 executes deterministic exact-revision events across:

- G0 standard delivery
- G1 standard delivery
- G2 standard delivery
- G3 standard delivery
- G2 approval wait/resume
- G5 CI recovery
- read-only projection
- G2 package export
- G3 scale control
- G5 scale control

G4 and G6 are explicit typed non-applicable shadow boundaries for the current route packs; no node selection at those boundaries is treated as success only when the report records that typed boundary explicitly.

Completion requires all 81 canonical IDs to appear in deterministic replay coverage. Slot 82 or any extension registry entry cannot satisfy the baseline count.

## E1 evidence

Two E1 evidence types are kept distinct:

1. **Live PR observation** — the real GitHub pull-request event is processed by the W4 shadow observer and W5 telemetry ledger. Nodes selected by that actual event may be marked E5 observed.
2. **Exact-head canary** — the CI run exercises RP-01 through RP-06 and G0-G6 boundaries against the same PR head. Canary evidence proves integration breadth but does not inflate `observed_live_count`.

## Safety/adversarial qualification

The final report must prove:

- central kill switch fails closed;
- exact revision drift fails closed;
- unknown scenario is typed, not guessed;
- repeated E0 execution is deterministic;
- every replayed node has `authority_granted=false`;
- every replayed node has `executed_effects=[]`;
- the canonical registry contains exactly 81 unique baseline IDs.

W5 independently rejects unsafe telemetry events, non-deterministic duplicate invocation results, and false-allow comparisons.

## Semantic-source audit

Each qualification record includes one of:

- `SOURCE_RESOLVED_EVALUATOR`
- `NAMED_TOOL_PRESENT`
- `DESCRIPTOR_ONLY`

Descriptor-only does not prevent a node from participating in shadow observation/replay, because SCRUM-566 is an evidence-collection program. It **does** prevent W6 from representing the node as authoritative-ready. Promotion to real/authoritative behavior remains a separately governed E2 promotion program.

## Closure rule

SCRUM-566 may only claim canonical-81 shadow enablement when the exact-head qualification report is PASS with:

- canonical_node_count = 81
- adapter_bound_count = 81
- route_bound_count = 81
- replay_proven_count = 81
- shadow_enabled_count = 81
- zero errors
- all adversarial checks true
- six route packs present in E1 canary evidence
- G0-G6 present in the gate matrix, with explicit non-applicable boundaries where no node is designed to run

This is **not** an authoritative-node promotion claim.
