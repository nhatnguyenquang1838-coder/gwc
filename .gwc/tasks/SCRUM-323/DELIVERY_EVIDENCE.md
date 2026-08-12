# SCRUM-323 — Current-Task Delivery Evidence Map (NA81)

Exact SHA: `6b47742c1e74addc36da4180b8d6786727989158` (origin/pre-prod HEAD at delivery, includes SCRUM-315 merge)
Parent authority: `AR-SCRUM288-20260811-R4` (github-actions[bot] receipt 5251551984, manifest on issue #232)
Route: `AUTONOMOUS_TO_PREPROD_HUMAN_TO_MAIN`

## Classification: DELTA_REQUIRED (NOT VERIFIED_REUSE)

The current NA81 brief (SCRUM-323 / GitHub #258) requires promoting a Draft PR to
Ready for Review only when G3 PASS + required CI green + no blockers + the SAME exact
head, failing closed otherwise, granting no merge authority. The pre-existing
`promotion_controller.py` only created the immutable-cut Draft PR (`mark_ready_allowed=False`,
`autonomous_main_action_allowed` excluded `mark_ready_for_review`). It had NO function to
promote Draft -> Ready. Hence a real implementation delta exists.

## Requirement -> Code -> Test mapping (exact SHA)

| Requirement (SCRUM-323 brief) | Code | Test |
|---|---|---|
| Draft->Ready only after same-head G3 PASS + CI + no blockers | `promote_to_ready_for_review` guards all four | test_valid_promotion / negative tests below |
| Mixed/stale head keeps Draft (never promote) | `head_sha != reviewed_head_sha` -> BLOCKED MIXED_HEAD | test_mixed_head_blocked, test_invalid_sha_blocked |
| Stale/failing G3 -> BLOCKED (pending if queued) | `g3_conclusion != "pass"` | test_stale_g3_blocked, test_g3_pending |
| CI pending/fail/unavailable -> BLOCKED/PENDING | `required_ci_conclusion != "success"` | test_ci_fail_blocked, test_ci_pending, test_ci_unavailable_blocked |
| Blocker present -> BLOCKED | `blockers` non-empty | test_blocker_present |
| Not a live Draft PR -> BLOCKED | `draft=False` or `pr_open=False` | test_not_draft_blocked, test_pr_closed_blocked |
| Idempotent reconcile of already-Ready | `existing_ready` idempotency match -> READY_REPLAY readback | test_already_ready_replay |
| Ready grants NO merge authority | `main_merge_allowed=False` always | test_no_merge_authority, test_valid_promotion |
| Action gated on main boundary | `autonomous_main_action_allowed` adds `mark_ready_for_review` | test_mark_ready_action_allowed |

## Files changed (this delivery)
- `tools/node_architect/promotion_controller.py` (added `promote_to_ready_for_review`; `autonomous_main_action_allowed` now permits `mark_ready_for_review`)
- `tests/test_autonomous_promotion_controller_na81.py` (NEW, 14 tests — current-task mapping)
- `tests/test_autonomous_promotion_controller.py` (unchanged; backward-compat, 5/5 PASS)

## Verification
- `PYTHONPATH=tools python3 -m unittest tests.test_autonomous_promotion_controller_na81` -> 14/14 PASS
- `PYTHONPATH=tools python3 -m unittest tests.test_autonomous_promotion_controller` -> 5/5 PASS (backward compat)
- `PYTHONPATH=tools python3 tools/node_architect/validate_node_catalog_repo_delivery.py` -> REPO_DELIVERY_NODE_CATALOG_VALID

## Dependency safety
Claimed AUTHORIZED_READY per LIVE Jira issuelinks: SCRUM-323 has no `inwardIssue` (is-blocked-by)
link, so it is not blocked. Live links show 323 is UPSTREAM of SCRUM-321/342 (323 blocks them),
contrary to the stale description-text "predecessors 321+342"; live operational truth was treated
as authoritative per the task brief ("Live Jira links are operational dependency truth"). Both 321
and 342 are currently To Do and depend on this node's Ready-for-Review capability.

## Note on classification discipline
This node was inspected against the FULL Jira SCRUM-323 brief + GitHub #258 + descriptor BEFORE
classification. The brief carries a `No auto-close rule` (historical Done / existing Ready helper /
PR already Ready is NOT current-task proof). A bare status flip was avoided; a real delta + evidence
map + tests were produced instead.
