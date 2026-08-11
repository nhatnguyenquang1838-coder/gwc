# SCRUM-323 — ready-for-review-promotion NA81 maturity

Promote a Draft PR to Ready for Review only when G3 PASS + required CI green + no
blockers bind the SAME exact head. Fails closed for mixed/stale head, pending/failing
G3/CI, or present blockers. Idempotent replay of already-Ready state. Grants no merge
authority (main promotion stays Human G4). Adds `promote_to_ready_for_review` to
`tools/node_architect/promotion_controller.py` + 14 NA81 tests.
