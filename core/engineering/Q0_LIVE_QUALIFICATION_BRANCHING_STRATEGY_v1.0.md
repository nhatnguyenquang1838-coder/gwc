# Q0 Live Qualification Branching Strategy v1.0

## Purpose

Define the engineering branching and source-identity rules for live qualification runs that may discover and self-repair GWC runtime defects. The strategy separates protected integration (`main`) from the currently accepted live-qualified runtime baseline.

## Canonical model

Use **Linear Chained Defect Branches + SHA-based Q0 Baseline**.

Identities:

- `protected_base_sha`: exact protected `main` SHA captured when Q0 starts.
- `q0_baseline_sha`: latest cumulative SHA that reached `RUNTIME_FIXED`.
- `fix_base_sha`: exact `q0_baseline_sha` from which one defect branch is created.
- `candidate_fix_sha`: current immutable candidate commit for one defect.
- `certified_q0_sha`: cumulative SHA that passes the final clean-state Q0 certification matrix.

`main` is the protected integration/certification target. It is not the working oracle for live defect qualification.

## Branch taxonomy

Each material runtime defect uses one dedicated branch:

```text
fix/<task-id>-q0-<sequence>-<defect-slug>
```

Example:

```text
main@P0
  └─ fix/SCRUM-781-q0-01-route-selection → A1 (accepted)
       └─ fix/SCRUM-781-q0-02-g2-validator → A2 (accepted)
            └─ fix/SCRUM-781-q0-03-producer-liveness → A3 (accepted)
```

Branch N+1 MUST start from the exact accepted SHA of branch N. No intermediate integration branch is required.

## Worktree isolation

One defect equals one branch, one isolated worktree, one bounded write scope, one incident fixture, and one acceptance chain.

A worktree containing foreign or unknown dirty state MUST NOT be cleaned, reset, stashed automatically, overwritten, or reused. Preserve it as evidence and create a fresh isolated worktree.

Accepted worktrees MAY remain read-only until Q0 certification closes for forensic replay.

## Commit and evidence immutability

A defect branch MAY contain multiple commits while the same root cause is being repaired. After any SHA is referenced by `LOAD_PROOF`, replay evidence, or baseline promotion, that SHA is immutable evidence.

After evidence exists:

- no amend;
- no interactive rebase;
- no force push;
- no history rewrite.

If replay fails, append another commit and produce a new candidate SHA.

## Baseline promotion

A candidate SHA may become the next `q0_baseline_sha` only when all are true:

1. `FIX_IMPLEMENTED` — original RED regression is GREEN on the bounded source fix;
2. `FIX_LOADED` — active runtime proves it consumes the candidate identity;
3. `FIX_REPLAY_VERIFIED` — the original incident passes on the loaded identity and execution advances at least one legal state beyond the old failure;
4. `RUNTIME_FIXED` — exact readback plus broader relevant regression passes, and stale dependent state has been invalidated/regenerated.

Focused GREEN alone MUST NOT promote the baseline.

## Same defect versus new defect

If replay fails for the same root cause, remain on the same defect branch and append a commit.

If the original failure is cleared, the current fix is accepted, and execution later exposes an independent root cause, first promote the accepted SHA to `q0_baseline_sha`, then create a new defect branch from that SHA.

## Protected-base drift

Do not automatically rebase a live-qualified lineage when `main` moves.

Classify protected-base drift:

- irrelevant to Q0 scope: continue the pinned Q0 lineage;
- relevant but validation-only impact: revalidate affected checks;
- material to runtime semantics, governance, authority, or in-scope source: immutable replan / reapproval;
- conflicting or unsafe: stop.

Never rebase or rewrite a lineage that already owns replay evidence.

## Integration boundary

Q0 qualification proves runtime behavior. Protected-main integration is a separate gate/action.

The final accepted lineage may be proposed for a governed PR. If integration produces a different commit identity (merge or squash SHA), post-integration target validation must bind to that resulting identity before it is called integrated/certified.

## Invariants

```text
NO_SHARED_WORKTREE
NO_DIRECT_MAIN_MUTATION
NO_FIX_WITHOUT_RED
NO_RUNTIME_FIX_WITHOUT_LOAD
NO_LOAD_WITHOUT_IDENTITY_PROOF
NO_ACCEPTANCE_WITHOUT_ORIGINAL_INCIDENT_REPLAY
NO_BASELINE_PROMOTION_WITHOUT_ADVANCE_BEYOND_FAILURE
NO_HISTORY_REWRITE_AFTER_EVIDENCE
NO_AUTOMATIC_REBASE_ON_MAIN_DRIFT
NO_NEW_DEFECT_INSIDE_AN_ACCEPTED_DEFECT_SCOPE
```
