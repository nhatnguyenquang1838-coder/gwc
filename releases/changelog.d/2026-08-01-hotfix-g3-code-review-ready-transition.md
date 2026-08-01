# G3 code-review-agent to Ready-for-Review hotfix

- Require a schema-valid, exact-head, read-only `code_reviewer` invocation receipt before G3 review closure.
- Remove the direct `G3_REVIEW_PASSED -> merge_pending` state transition.
- Make successful Ready-for-Review promotion and PR readback the only G3 path into `merge_pending`.
- Strengthen the G3 repo-delivery and validation-quality node descriptions without adding an 82nd catalog node.
- Preserve separate G4 merge authority and all G5/G6 exclusions.
