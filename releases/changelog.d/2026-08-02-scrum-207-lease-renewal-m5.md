---
task_id: SCRUM-207
node_id: runtime_checkpoint.lease-renewal
maturity: M2 -> M5_REPLAY_SAFE
gate: G2_EXECUTION
summary: >
  Implement deterministic, replay-safe lease renewal (MAT-F4-N06).
  Renewal is gated on current owner identity, unexpired/policy-renewable lease,
  matching task_id / scope_hash / base_sha / fencing token. Fencing token is
  advanced monotonically; base drift, approval expiry, scope drift, and stale
  worker state are surfaced as explicit reconcile routes (never blind retry).
tests:
  - tests/test_lease_renewal.py (14 tests covering EARS #1-#4 contract)
verified:
  - PYTHONPATH=tools python tests/test_lease_renewal.py -> 14 passed
exclusions:
  - merge_to_main, deploy, release, edit_core_governance, credentials,
    migrations, manual_g5_deploy, recursive_evidence_pr
