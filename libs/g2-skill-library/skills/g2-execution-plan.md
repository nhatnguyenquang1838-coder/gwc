# G2 Execution Plan Blueprint

## Purpose
This document provides the machine-readable, step-by-step instructions for transitioning from a high-level G1 decision (e.g., "Fix typo in README") to low-level, transactional repository mutations (e.g., `add_file`, `commit`, `push`).

## Execution Model: Transactional Sequence
G2 actions are never performed in a batch; they must be executed as an ordered sequence of atomic transactions.

**Input:** `G1_APPROVAL_HASH` (The immutable signature confirming intent and scope).
**Output:** A linear, verified sequence of operations leading to the G3 ready state.

### Transaction Sequence Steps (Blueprint)

1. **Identify Target:** Locate the file paths and line ranges affected by the G1 approval hash.
2. **Generate Delta:** Compute the required change (`diff`) based on the approved intent vs. current base SHA.
3. **Apply Change:** Apply the patch/diff to a new, isolated working tree branch.
4. **Validate Action:** Run local checks against the `libs/g2-repository-interaction.md` constraints (e.g., "Is this action within the approved scope?").
5. **Finalize Transaction:** Create a commit object containing the change and map it to the G2 execution record.

### Context7 Integration in Action
When `CONTEXT7_LIVE` mode is used, this blueprint queries the Context7 transaction engine for:
*   **Optimal Path:** The most efficient sequence of transactions based on current codebase state.
*   **Pre-emptive Guarding:** Checks for potential conflicts or drifts before commit, based on the approved G1 boundary.

When `OFFLINE_EXECUTABLE` mode is used, this blueprint follows the pinned sequence defined at the time of G1 approval.

## Actionable Protocol
The plan must always be actionable and auditable, linking each command execution back to the G1 approval hash.

**Example Action Sequence (Conceptual):**
1. `checkout(base_sha)`
2. `apply_patch(path/to/file, patch_id)`
3. `add_gwc_commit(message="G2fix: Implement approved changes")`
4. `create_garded_branch()`

## G1 implementation-plan handoff precondition

Before the first G2 repository mutation, the executor MUST read the exact plan package referenced by the accepted G1 decision and G2 execution envelope.

When `implementation_plan.applicability=required`, G2 MUST:

1. read `requirements.md`, `design.md`, and `tasks.md`, or the approved equivalent package;
2. verify `canonical_task_uid`, repository, protected-base SHA, plan root, and plan revision against G1;
3. verify the current repository still matches the protected-base binding and that the approved scope remains consistent;
4. write `g2/plan-read-receipt.yaml` with the exact paths read, revision, base SHA, reader, timestamp, and `VERIFIED` result;
5. run `tools/validate_g01.py --gate G2_EXECUTION` before the first mutation.

A missing plan, missing read receipt, stale revision, base drift, ownership conflict, unresolved dependency, or scope mismatch MUST stop execution and return the task to G1. G2 MUST NOT silently regenerate or broaden the implementation plan.

`PLAN_NOT_APPLICABLE` is valid only when the accepted G1 evidence includes a reason and the G2 envelope carries the same not-applicable reference. This precondition grants no merge, deploy, release, credential, migration, production-configuration, or production-data authority.
