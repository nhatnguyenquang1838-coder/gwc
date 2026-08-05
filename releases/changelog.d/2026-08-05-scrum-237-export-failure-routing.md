---
id: SCRUM-237
title: package_export.export-failure-routing (M5_REPLAY_SAFE)
type: feature
family: package_export
nodes: [package-export-export-failure-routing]
summary: >
  Recommend-only failure router mapping every upstream package_export reason code
  to exactly one bounded action (REPAIR_INPUT, REBUILD_STAGING, REVERIFY_READBACK,
  BOUNDED_RETRY, HUMAN_REQUIRED, FAIL_CLOSED). Deterministic decision table, replay-safe
  route digest, bounded retry with reconciled-readback requirement. Completes the nine-node
  package_export family. Grants no publish/merge/deploy authority.
authority_boundary: g2_required
gates: [G2_EXECUTION, G3_PR]
