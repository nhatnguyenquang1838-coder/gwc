# SCRUM-325 — Checkpoint capture NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `runtime_checkpoint.checkpoint-capture` from a historical M4 primitive
to an instruction-backed executable NA81 node. Capture now fails closed on
secrets, overbroad/unbounded state and key/byte bounds, keeping the replay
state minimal and deterministic while granting no later-gate authority.

## Guardrails

```text
Checkpoint capture excludes secrets, caches, and unbounded working memory.
Capture performs no effect and grants no G4/G5/G6 authority.
No projection-only evidence is treated as canonical proof.
```
