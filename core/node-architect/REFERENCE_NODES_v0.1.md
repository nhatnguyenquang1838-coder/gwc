# Reference Nodes v0.1

Status: active  
Scope: REVAMP-GWC-011 reference nodes only

## Purpose

This document defines three reference nodes used to prove the Runtime Kernel and schemas before expanding the node catalog.

The reference nodes are intentionally small:

1. `reference.read_context` — read-only node.
2. `reference.scoped_write` — bounded side-effect node.
3. `reference.await_approval` — suspend/resume node.

## Design rules

- Each node is data-only JSON under `core/node-architect/reference-nodes/`.
- Each node has a `node_class`, `entry`, `do`, `branches`, `exit`, and `next` contract.
- Read-only nodes must not declare side effects.
- Side-effect nodes must declare an idempotency key and a read-back node.
- Suspend/resume nodes must checkpoint before suspend and define a resume signal.
- These examples are not the 81-node catalog.

## Node flow

```mermaid
flowchart LR
  A[reference.read_context] --> B[reference.scoped_write]
  B --> C[reference.await_approval]
  C --> D[Next governed task]
```

## Authority boundary

Reference nodes are contract examples and validation fixtures only. They do not grant protected-branch write outside G2, merge, auto-merge, deploy, release, production configuration, credential, migration, production-data, force-push, branch-deletion, or PR-base-change authority.

## Compatibility

These nodes reuse the Runtime Kernel and existing runtime schema layer. They do not replace G0-G6, checkpoint/resume, or package-export behavior.
