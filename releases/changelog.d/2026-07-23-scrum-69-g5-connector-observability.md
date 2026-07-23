## SCRUM-69 post-merge G5 connector observability fix

### Added

- Exact post-merge verification procedure for read-only `G5_STATUS_VERIFY`:
  agents must first attempt `event=push`, `branch=main`, and
  `head_sha=<merge_sha>` lookup, then fall back to known `run_id` and direct
  jobs/artifacts lookup when the connector surface does not support those
  filters or returns empty results.
- `CONNECTOR_OBSERVABILITY_INCOMPLETE` classification path so empty
  PR-filtered results no longer get misreported as `CI_PENDING` unless an
  exact post-merge run is still in progress.

### Changed

- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md` -> `v1.1`
- `core/E2E_DRAFT_PR_DELIVERY_RULE.md`
- `AGENTS.md`
- `agents/dwc/agent-instructions.md`
- `agents/chatgpt-agent/agent-instructions.md`
- `tests/test_gate_lifecycle_process_contract.py`
- `tests/test_fastlane_process_optimization.py`

### Safety

- Read-only verification only. No merge, deploy, release, production-data,
  credential, or migration authority is added.
