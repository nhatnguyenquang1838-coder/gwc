# SCRUM-324 repo_delivery.pr-blocker-check NA81 blocker taxonomy delta

- Extended `decide_pr_blocker_check` from a binary `CLEAR|BLOCKED` to a
  four-state taxonomy matching the current NA81 brief: `CLEAR`, `BLOCKED`,
  `PENDING_RETRY`, `HUMAN_REQUIRED`.
- Non-terminal CI (in_progress / queued / missing required checks) now produces
  `PENDING_RETRY` instead of being silently treated as CLEAR.
- Unsupported / empty reviewer evidence produces `HUMAN_REQUIRED` so stale
  approvals cannot self-grant readiness.
- Outcome precedence: BLOCKED > HUMAN_REQUIRED > PENDING_RETRY > CLEAR.
- Readiness never grants merge / deploy / production authority (authority-negative
  preserved across all four outcomes).
- Added focused NA81 tests `tests/test_repo_delivery_pr_blocker_check_na81.py`
  covering: clean PR, CI pending/queued/unavailable, CI failure, unsupported
  reviewer, no reviews, stale check, head SHA mismatch, authority-never-granted
  invariant, digest determinism.
