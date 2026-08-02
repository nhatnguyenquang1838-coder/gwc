# SCRUM-202 — runtime_checkpoint.checkpoint-capture (MAT-F4-N01)

```text
Task: SCRUM-202
Node: runtime_checkpoint.checkpoint-capture
Family: runtime_checkpoint
Maturity: M2 -> M5_REPLAY_SAFE
Authority boundary: G2_EXECUTION
```

## Added

- Added `tools/node_architect/checkpoint_capture.py`: a deterministic, replay-safe
  checkpoint capture node implementation.
  - `capture_checkpoint(...)` produces a normalized snapshot bound to
    `task_id`, `run_id`, `node_id`, `gate`, `base_sha`, `head_sha`, `scope_hash`,
    `graph_revision`, and `repository`.
  - Deterministic digest: identical input yields an identical `state_digest`.
  - Fail-closed binding: rejects capture when task/repository/scope/gate identity
    is missing or ambiguous.
  - Pending-action capture carries exact `action_id`, `target`, `authority_gate`,
    and `idempotency_key`.
  - `reconstruct_next_action(...)` provides replay-read compatibility so a resume
    can rebuild the exact next action without allowing stale worker advancement.
- Added `tests/test_checkpoint_capture.py` covering deterministic digest, missing
  binding rejection, pending-action capture, crash-before-persist, and
  replay-read compatibility.
- Added the G0/G1/G2/G3 task-scoped gate artifacts under
  `.gwc/tasks/SCRUM-202/`.

## Guardrails

```text
No merge authority.
No deploy/release.
No production data/config.
No runtime engine / scheduler / worker implementation.
No scope expansion beyond the approved node.
```
