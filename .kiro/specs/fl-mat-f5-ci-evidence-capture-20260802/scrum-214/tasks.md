# SCRUM-214 — Implementation Tasks

1. Add RED tests for terminal success/failure/cancelled and exact-SHA mismatch.
2. Add RED tests for pending, unavailable, empty results and timeout checkpoint-before-wait behavior.
3. Add RED tests for head drift, duplicate callback, crash-after-capture and deterministic replay.
4. Add a closed Draft 2020-12 decision/evidence schema.
5. Implement the narrow CI-evidence adapter by reusing current CI capture and checkpoint primitives.
6. Bind the SCRUM-214 handler in `client_runtime.py`; do not implement SCRUM-215/219.
7. Run focused tests, schema checks, compileall and complete-diff review.
8. Push only after exact G2 approval, open a Draft PR, monitor exact-head CI and perform independent G3 review.
