# Intake Context Node Family v0.1

```text
Task: REVAMP-GWC-016
Batch: batch-01-intake-context
Family: intake_context
Authority boundary: G0_CONTEXT
Planned nodes: 9
Runtime behavior change: none
```

## Purpose

This family adds the first controlled node catalog batch after the controlled 81-node expansion plan.

The nodes are **read-only G0 context nodes**. They structure request intake, source resolution, repository identity, protected base capture, risk classification, read/write scope rendering, intake-card rendering, and context-gap escalation.

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
| `intake_context.request-intake` | Normalize the user request into a bounded intake fact set. |
| `intake_context.source-resolution` | Resolve REPO / PACKAGE / MIXED source instruction. |
| `intake_context.repo-identity-check` | Verify repository identity, default branch, protected branch, and execution mode assumptions. |
| `intake_context.protected-base-capture` | Capture exact protected-base SHA for later evidence. |
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
