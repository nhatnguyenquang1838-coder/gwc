# SCRUM-210 — runtime_checkpoint.checkpoint-expiry-cleanup (MAT-F4-N09)

```text
Task: SCRUM-210
Node: runtime_checkpoint.checkpoint-expiry-cleanup
Family: runtime_checkpoint
Maturity: M1 -> M5_REPLAY_SAFE
Authority boundary: G2_EXECUTION
```

## Added

- Added `tools/node_architect/checkpoint_expiry_cleanup.py`: a deterministic, replay-safe local expiry-cleanup primitive (MAT-F4-N09, M5_REPLAY_SAFE).
  - It tombstones only expired disposable `resume-hint` and `interrupt-frame` entries.
  - Governance, audit, and append-only runtime evidence are retained; valid active-resume paths take precedence.
  - It emits auditable `TOMBSTONE` markers and deterministic cleanup digests.
- Verified that the protected base already contains `core/node-architect/node-catalog/runtime_checkpoint/checkpoint-expiry-cleanup.node.json`, byte-identical to the PR #195 candidate. It is the canonical metadata-only descriptor for `runtime_checkpoint.checkpoint-expiry-cleanup`, bound to `G2_EXECUTION`; no scheduler or orchestration wiring is introduced.
- Added `tests/test_checkpoint_expiry_cleanup.py` with 13 focused tests. Its repository-local import boundary avoids host-level `tools` package shadowing.
- Added fresh task-scoped G0/G1/G2 R3 evidence under `.gwc/tasks/SCRUM-210/` and the R3 Kiro plan under `.kiro/specs/scrum-210-checkpoint-expiry-cleanup/`.

## Validation

- Expected RED before implementation: direct focused test failed only because `node_architect.checkpoint_expiry_cleanup` was absent.
- GREEN: `uv run --python 3.11 python tests/test_checkpoint_expiry_cleanup.py` -> 13 passed.
- GREEN: `uv run --python 3.11 python -m unittest discover -s tests -p 'test_checkpoint_expiry_cleanup.py'` -> 13 passed.
- G0/G1/G2 receipt validation: `tools/validate_g01.py --workspace .gwc/tasks/SCRUM-210 --gate G2_EXECUTION --json` -> PASS.

## Guardrails

```text
No merge authority.
No deploy/release.
No production data/configuration.
No runtime engine, scheduler, or worker implementation.
No scope expansion beyond the approved local primitive, catalog descriptor, focused test, Kiro plan, changelog, and task evidence.
```
