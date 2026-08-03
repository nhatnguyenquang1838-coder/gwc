# Design Document

## Overview

The delivery adds `tools/node_architect/checkpoint_expiry_cleanup.py` and a portable focused test. It verifies the already-present canonical Node Architect catalog descriptor as a prerequisite, ports the PR #195 candidate after a test-first red check, and keeps discovery metadata separate from runtime orchestration.

## Architecture

`CleanupEntry` and `CleanupPolicy` are immutable inputs. `classify_entry` applies a priority order: governance/audit retention, append-only retention, valid active-resume retention, then expired disposable tombstoning. `plan_cleanup` sorts the resulting IDs and emits a canonical digest. `apply_cleanup` turns selected entries into tombstone markers and emits a replay-readable result. The node catalog JSON only names this capability and its G2 authority boundary; it does not invoke it.

## Components and Interfaces

- `CleanupEntry`: typed registry record with artifact type, retention class, expiry, and tombstone state. (R1, R2)
- `CleanupPolicy`: clock plus optional active-resume binding. (R1, R3)
- `classify_entry`, `plan_cleanup`, `apply_cleanup`: pure evaluation and state transformation functions. (R1-R3)
- `is_replay_equivalent`: compares deterministic cleanup cores while ignoring run identity/time. (R1)
- CLI: loads one local JSON payload and prints plan/result JSON. (R4)
- Existing `runtime_checkpoint/checkpoint-expiry-cleanup.node.json`: verified canonical discovery descriptor with `g2_required` authority boundary; it is not modified by this delivery. (R5)

## Data Models

No persistent store, schema, migration, or external interface is introduced. Tombstones are in-memory records in the returned result; existing `canonical_json`/`digest_payload` conventions are reused from `checkpoint_store.py` and `lease_expiry_recovery.py`.

## Correctness Properties

- **CP-1 (R1):** the plan is deterministic because selected IDs are sorted and the digest is canonical JSON.
- **CP-2 (R2):** governance, audit, and retained append-only evidence are never selected for tombstoning.
- **CP-3 (R3):** a valid active resume binding takes priority over expiry cleanup.
- **CP-4 (R1/R2):** a second run on the same input is replay-equivalent and does not add a new tombstone for an already tombstoned entry.

## Error Handling

Malformed JSON or incompatible dataclass payloads fail in the local CLI process. The module contains no retry loop and no connector, filesystem mutation beyond caller-supplied local CLI input read, or production behavior.

## Testing Strategy

First port only the focused test with the repository-tools import repair and run it against the absent cleanup module to observe the expected import failure (RED). Then port the #195 module, run the 13 focused tests to GREEN, and validate both direct-file and `unittest discover` invocation under Python 3.11. The existing catalog descriptor is checked for node ID, canonical status, and `g2_required` boundary without modifying it.

## Implementation Constraints

- Reuse existing digest semantics; do not introduce dependencies.
- Keep mutation scope to the module, focused test, changelog, Kiro plan, and task artifacts; validate but do not modify the canonical node descriptor.
- Do not integrate the node into runtime orchestration, scheduler, deployment, data migration, or production services.
- G2 approval is required before repository worktree/branch creation or any repository write.
