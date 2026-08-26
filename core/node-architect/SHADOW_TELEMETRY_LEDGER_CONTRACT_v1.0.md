# Shadow Telemetry Ledger Contract v1.0

## Purpose

The Node Architect shadow evidence plane records what a shadow node observed or recommended without changing the authoritative GWC gate/runtime path.

## Authority invariant

Telemetry, comparisons, confidence, and MoA synthesis are evidence only. They cannot grant or widen G2-G6 authority, execute a side effect, transition a gate, or mutate canonical runtime evidence.

A telemetry event is rejected if the source result reports `authority_granted=true` or a non-empty `executed_effects` list.

## Invocation identity

Each logical node invocation is keyed by task ID, run ID, gate, exact repository revision, node ID/version, route pack, and route/graph revision.

The idempotency key excludes volatile timing/cost data and result content. Replaying the same logical invocation with the same event digest is a duplicate. Replaying the same invocation identity with a different event digest is `SHADOW_REPLAY_NON_DETERMINISTIC` and fails closed.

## Append-only behavior

The canonical run-scoped representation is JSON Lines. Existing malformed ledger lines are treated as corruption, not skipped. Duplicate logical invocations are not appended twice.

## Authoritative comparison

Shadow and authoritative outcomes are comparable only when task, run, gate, and exact revision match. Supported comparison classes are:

- `AGREEMENT`
- `SHADOW_MORE_CONSERVATIVE`
- `SHADOW_MORE_PERMISSIVE_DENIED`
- `CONTRADICTION_UNRESOLVED`
- `INSUFFICIENT_EVIDENCE`
- `NOT_COMPARABLE`

A shadow ALLOW/PASS/PROCEED against an authoritative BLOCK/DENY is explicitly classified as `SHADOW_MORE_PERMISSIVE_DENIED` because false-allow evidence is safety-critical.

## MoA synthesis

Allowed synthesis outcomes are exactly `CONSENSUS`, `CONTRADICTION_UNRESOLVED`, and `INSUFFICIENT_EVIDENCE`. Minority contradiction evidence is copied into the synthesis output and cannot be erased by majority voting.

## Live observer integration

The PR shadow-observer workflow materializes an immutable G3 event, runs the W4 shadow orchestrator, converts every selected-node result into telemetry, writes `shadow-ledger.jsonl`, and uploads the event, output, ledger, and telemetry summary as workflow artifacts.

This workflow remains non-authoritative and read-only with respect to repository/runtime state.
