# G2 Repository Interaction Constraint Layer

## Purpose
This document serves as the immutable, read-only registry of actions permitted under a G2_EXECUTION phase. It prevents scope creep and unauthorized commands by mapping all proposed actions against the boundaries set in the G1 Approval Envelope.

## Binding Constraint
All actions must fall under one of these allowed categories and cannot exceed the boundaries defined by the G1 decision record.

### Allowed Actions (G2_EXECUTION)
*   `Add/Modify File`: Restricted to changes within the defined paths and line ranges approved in G1.
*   `Commit`: Restricted to a single, logical, atomic commit representing the culmination of G2 work.
*   `Create Branch/Worktree`: Initiated from a known, valid base SHA (G0 verification).
*   `Push/Update Ref`: Authorized only as the final step of G2, transitioning to a guarded state ready for review.

### Prohibited Actions (Hard Exclusions)
Any attempt to execute the following actions without G3/G4 gatekeepers will result in immediate failure and G2 rollback:
*   Direct write to protected branches.
*   Squashing/Rewriting shared history (`git reset --hard`, `amend`).
*   Changing the target base branch/SHA after G1 approval.
*   Merging or tagging releases.

**Enforcement:** The execution layer must verify that the action aligns with the `G1_APPROVAL_HASH` *before* interacting with the repository. If mismatch occurs, the action is blocked, and a `G2_ACTION_NOT_AUTHORIZED` failure code is logged.