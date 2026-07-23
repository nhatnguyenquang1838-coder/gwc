# REVAMP-GWC-024 — Failure recovery node family

Adds Batch 08 `failure_recovery` with exactly nine runtime-node descriptors for timeout, crash, stale-session reconciliation, ambiguous-write readback, CAS conflict, lease/approval expiry, duplicate-agent fencing, and version-drift rollback routing.

The batch reuses the Runtime Kernel, Checkpoint Resume Rule, stale-session cleanup rule, and failure-simulation matrix. It does not implement a scheduler, worker, deployment engine, package publish, consumer mutation, production behavior, or Batch 09 `scale_control`.
