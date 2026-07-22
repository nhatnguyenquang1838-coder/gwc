# REVAMP-GWC-019 — Runtime checkpoint node family

```text
Task: REVAMP-GWC-019
Batch: batch-04-runtime-checkpoint
Family: runtime_checkpoint
Planned nodes: 9
Authority boundary: G2_EXECUTION
```

## Added

- Added the `runtime_checkpoint` controlled node catalog family.
- Added 9 checkpoint/resume nodes:
  - `runtime_checkpoint.checkpoint-capture`
  - `runtime_checkpoint.checkpoint-persist`
  - `runtime_checkpoint.resume-token-generation`
  - `runtime_checkpoint.resume-token-validation`
  - `runtime_checkpoint.lease-acquisition`
  - `runtime_checkpoint.lease-renewal`
  - `runtime_checkpoint.cas-write-guard`
  - `runtime_checkpoint.state-reconciliation`
  - `runtime_checkpoint.checkpoint-expiry-cleanup`
- Added a stdlib validator for the family.
- Added unit tests covering valid family shape, wrong authority, wrong gates, extra fields, and missing-node failure.

## Guardrails

```text
No all-81 implementation.
No runtime engine.
No scheduler/worker.
No production data/config.
No deploy/release.
No merge authority.
```
