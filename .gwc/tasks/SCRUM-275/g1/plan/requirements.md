# SCRUM-275 Implementation Requirements

**Task:** [APR-MVP-05] Pre-prod branch, PR, CI, independent review and governed merge
**Parent:** SCRUM-270 (Autonomous Pre-Prod Runtime MVP)
**Base SHA:** `2e20badf04b4d84bf8a2e88d6e1e88d540745d35` (current `origin/main`)
**Run ID:** g1-SCRUM-275-20260808-1839

## Goal
Implement the real repository-delivery path for one autonomous task from the
protected `pre-prod` SHA through exact-head G3 evidence and standing-policy G4
merge into `pre-prod` only.

## Functional requirements

1. **Pre-prod bootstrap** — Provide a guarded bootstrap that creates the
   protected `pre-prod` branch from an explicitly approved `main` SHA, enforcing
   that `pre-prod` may never be pushed to directly and is never an autonomous
   merge target of `main`.
2. **Task branch isolation** — Create one isolated task branch
   `auto/<run-id>/<task-id>` from the latest verified `pre-prod` SHA.
3. **Draft PR** — Create or update a Draft PR targeting `pre-prod` only
   (never `main`), using the runtime graph/story renderer delivered by SCRUM-271.
4. **Exact-head CI + review** — Run exact-head required CI and an independent
   read-only reviewer (or honest fresh-context fallback) before Ready-for-Review.
5. **G3 readiness closure** — Close findings through bounded G2 repair; every
   changed head invalidates prior review, CI, PR description and G4 evidence.
6. **G4 standing-policy receipt** — Validate the standing-policy G4 receipt
   from SCRUM-272; merge only with a non-expired, head-bound receipt.
7. **Governed merge** — Merge with the configured method (squash for MVP) into
   `pre-prod` only and record canonical merge proof.

## Branch and PR guardrails (hard invariants)

```
allowed base: pre-prod
forbidden base: main
allowed head: auto/<run-id>/<task-id>
merge method: squash for MVP
force push: forbidden
PR base change: forbidden
branch deletion by autonomous runtime: forbidden in MVP
```

## G3/G4 evidence chain (must bind)

- task and run identity;
- current pre-prod base SHA;
- exact PR head SHA;
- current PR number and `draft=false` readback;
- complete diff and changed-path digest;
- exact-head CI conclusions;
- independent review receipt and findings closure;
- G3 delivery decision;
- managed PR-body digest;
- runtime graph digest and gate-story digest;
- standing-policy revision and non-expired G4 receipt.

## Non-requirements (explicit)

- No deploy, release, or production authority is inferred from merge success.
- Existing G3/G4 regression suites must remain green.
- The autonomous runtime does not delete branches in MVP.
