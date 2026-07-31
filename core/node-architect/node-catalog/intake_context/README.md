# Intake Context Node Family v0.1

```text
Task: REVAMP-GWC-016
Batch: batch-01-intake-context
Family: intake_context
Authority boundary: G0_CONTEXT
Planned nodes: 9
Runtime behavior change: none

SCRUM-176 Update (2026-07-31)
- Source resolution extended with typed contract (intent, outcome, constraints, exclusions, entry_guards, reason_codes)
- Exact-head CI evidence: main@3a0bee57058672e4167bac0ea5ff02b3ac9080d9
- Validator: tools/node_architect/validate_node_catalog_intake_context.py
- Tests: tests/test_node_catalog_intake_context.py (16 tests PASS)
```

## Purpose

This family adds the first controlled node catalog batch after the controlled 81-node expansion plan.

The nodes are **read-only G0 context nodes**. They structure request intake, source resolution, repository identity, protected base capture, risk classification, read/write scope rendering, intake-card rendering, and context-gap escalation.

## Source Resolution Typed Contract

The `intake_context.source-resolution` node extends the basic descriptor with typed fields:

| Field | Type | Purpose |
|---|---|---|
| `intent` | string | Describes the purpose of source resolution |
| `outcome` | string | Describes the expected typed result |
| `constraints` | string[] | Bounded rules for deterministic resolution |
| `exclusions` | string[] | Bounded exclusions (no runtime behavior, deployment, migration, credentials) |
| `entry_guards` | string[] | Required gates and authority boundaries |
| `reason_codes` | string\|object | Stable machine-readable codes (ACCEPTED, AMBIGUOUS, MALFORMED, MISSING_EVIDENCE, INVALID_MODE) |

**Deterministic resolution:** Source mode must be resolved as `REPO`, `PACKAGE`, or `MIXED` deterministically.

**Fail closed:** When source authority cannot be distinguished, reject with a stable reason code.

**Provenance:** Evidence must be verified, not guessed.

## Guardrails

```text
✅ exactly 9 nodes
✅ all nodes belong to intake_context
✅ all nodes are limited to G0_CONTEXT
✅ no production runtime behavior
✅ no scheduler / worker / storage adapter
✅ no G2/G3/G4/G5/G6 authority
```

## Nodes

| Node | Purpose |
|---|---|
| `intake_context.request-intake` | Normalize the user request into a typed intake contract with intent, outcome, constraints, exclusions, entry_guards, and reason_codes while preserving G0_CONTEXT gate and read_only authority. |
| `intake_context.source-resolution` | Resolve REPO / PACKAGE / MIXED source instruction. |
| `intake_context.repo-identity-check` | Verify repository identity, default branch, protected branch, and execution mode assumptions. |
| `intake_context.protected-base-capture` | Capture exact protected-base SHA and typed readback/drift evidence for later validation. |
| `intake_context.risk-classification` | Classify risk flags before gate routing. |
| `intake_context.files-read-scope` | Render required reads for the current task. |
| `intake_context.files-write-scope` | Render bounded write paths and exclusions. |
| `intake_context.intake-card-render` | Produce the standard GWC intake card. |
| `intake_context.context-gap-escalation` | Fail closed when required context or evidence is missing. |

## Validation

Run:

```bash
python tools/node_architect/validate_node_catalog_intake_context.py
python -m unittest tests/test_node_catalog_intake_context.py
```

## Compatibility

This batch extends the runtime kernel and the controlled catalog plan. It does not replace existing reference nodes, checkpoint contracts, simulation rules, or package export rules.

## Impact

```text
✅ adds 9 catalog node definitions
✅ adds a family README
✅ adds a stdlib validator
✅ adds tests
❌ does not implement all 81 nodes
❌ does not change runtime behavior
```
