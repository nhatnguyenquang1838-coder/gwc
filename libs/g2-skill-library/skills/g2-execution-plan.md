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