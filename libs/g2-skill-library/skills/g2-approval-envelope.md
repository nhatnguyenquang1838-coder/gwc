# G2 Approval Envelope Generation

## Purpose
This artifact captures the culmination of all successful G2 execution steps and formats them into a reviewable, auditable package suitable for entering the G3 PR phase. It is the bridge between machine execution and human review.

## Contents
The envelope must contain, but is not limited to:
1. **G0/G1 Provenance:** Links back to the initial approved intent (`G1_APPROVAL_HASH`).
2. **Execution Log:** A timeline of all successful low-level transactions (e.g., `apply_patch`, `commit`) performed on the isolated worktree.
3. **Head SHA:** The unique SHA of the resulting branch tip. This is the official artifact being submitted for review.
4. **Diff Artifact:** The complete, machine-generated diff between the base SHA and the current HEAD SHA.
5. **Validation Receipt:** Proof that the isolation checks passed (e.g., "No accidental deletion," "No secrets introduced").

## Transition Rule
The G2 execution is deemed complete and ready for handover when this envelope exists, is schema-valid, and has been checked into the repository. Submission of this validated envelope triggers the G3 phase review lifecycle.

**Crucial Constraint:** The G2 system *cannot* proceed to G3 until this envelope is present, validated against the G1 intent, and signed off as complete by the execution logic.