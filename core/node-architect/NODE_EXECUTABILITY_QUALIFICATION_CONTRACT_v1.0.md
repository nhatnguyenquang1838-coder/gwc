# Node Architect Executability Qualification Contract v1.0

## Purpose

This contract separates Node Architect catalogue/maturity state from runtime executability. A node is never considered executable merely because its descriptor exists, Jira is Done, or `source_status`/`maturity` is favorable.

## Qualification ladder

- `E0_CATALOGUED`: canonical ID/descriptor exists.
- `E1_INSTRUCTION_READY`: normalized `entry -> do -> branches -> exit -> next` shadow instruction exists.
- `E2_ADAPTER_BOUND`: a deterministic shadow adapter is bound.
- `E3_ROUTE_BOUND`: at least one source-backed route/gate binding exists.
- `E4_REPLAY_PROVEN`: deterministic replay/safety fixtures pass.
- `E5_OBSERVED`: governed live-shadow evidence exists.

## Canonical baseline

The baseline population is exactly 81 unique IDs from `core/node-architect/node-registry.json`. Post-81 extension nodes never count toward baseline coverage.

## Shadow invariants

All E1+ instructions run with:

```text
mode = shadow_readonly
authority = none
output_effect = observe_only
automatic_gate_advance = false
decision_authority = false
fail_closed = true
```

The executability view does not promote a node to authoritative runtime and does not grant G2-G6 authority.

## Proof rule

`runtime_executable=true` requires explicit adapter and route evidence. Maturity or `source_status` alone is insufficient.
