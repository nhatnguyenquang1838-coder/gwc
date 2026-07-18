---
id: dispatching-parallel-review
version: 0.1.0
role: optional
compatible_gate: G3_PR
source_type: gwc-normalized-offline-adaptation
upstream_reference: /obra/superpowers
---
# Dispatching Parallel Review — GWC Offline Adaptation

Use only when review lanes are independent. Each reviewer receives the same immutable evidence package and acts read-only. Record reviewer identity, lane, head SHA, and verdict.

One controller consolidates findings into one G3 decision. Any head SHA change invalidates all parallel results.
