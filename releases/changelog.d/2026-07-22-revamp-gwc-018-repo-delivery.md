# REVAMP-GWC-018 — Repo Delivery Node Family

```text
Task: REVAMP-GWC-018
Batch: batch-03-repo-delivery
Family: repo_delivery
```

## Added

- Add the `repo_delivery` node catalog family with exactly 9 nodes:
  - `repo_delivery.branch-creation`
  - `repo_delivery.base-drift-check`
  - `repo_delivery.scoped-file-write`
  - `repo_delivery.diff-readback`
  - `repo_delivery.draft-pr-creation`
  - `repo_delivery.ci-run-capture`
  - `repo_delivery.ci-failure-repair`
  - `repo_delivery.ready-for-review-promotion`
  - `repo_delivery.pr-blocker-check`
- Add family README and admission/guardrail notes.
- Add stdlib validator for node count, authority boundary, gate boundary, duplicate node IDs, and closed object keys.
- Add unit tests for valid and invalid catalog cases.
- Export the family, validator, tests, and changelog fragment through the GWC package manifest.

## Guardrails

```text
No merge authority.
No deploy/release authority.
No production config/data authority.
No runtime engine implementation.
No all-81 catalog implementation.
```
