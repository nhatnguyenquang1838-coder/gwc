# SCRUM-312 — Evidence artifact map NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `gate_authority.evidence-artifact-map` from a historical M4 mapper to
an instruction-backed executable NA81 node. The evaluator now resolves the
exact current gate/action evidence set, validates supplied schema/freshness/
presence and task/repository/base/head/scope bindings, emits typed fail-closed
gaps, and keeps replay digests stable.

## Guardrails

```text
The node is pure and offline.
Evidence mapping never grants gate, write, PR, merge, deploy, release, or production authority.
No projection-only evidence is treated as canonical proof.
```
