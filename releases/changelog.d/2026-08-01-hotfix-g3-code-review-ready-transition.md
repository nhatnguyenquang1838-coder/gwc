# G3-to-G5 governed delivery hotfix

- Require schema-valid, exact-head, independent read-only review evidence before G3 review closure, using an agent reviewer when available or an explicit human reviewer fallback in `chat_connector_only`.
- Remove the direct `G3_REVIEW_PASSED -> merge_pending` state transition.
- Make successful Ready-for-Review promotion and PR readback the only G3 path into `merge_pending`.
- Materialize human PR-comment G4 authority as a validated sanitized receipt without allowing the bot receipt to create authority.
- Record the GitHub `pull_request.closed` merge event as exact-head G4 merge proof.
- Keep G5 distinct from G4 and make the exact merge-SHA GitHub Actions artifact canonical machine evidence.
- Use the G5 PR comment for human traceability and keep Jira/Slack as `projection_only` surfaces.
- Persist pending G5 checkpoints externally and forbid evidence commits or recursive evidence PRs.
- Strengthen existing G3/G4/G5 Node Architect descriptors without adding an 82nd catalog node.
- Preserve separate G4 merge authority and all G5 manual-action/G6 exclusions.
