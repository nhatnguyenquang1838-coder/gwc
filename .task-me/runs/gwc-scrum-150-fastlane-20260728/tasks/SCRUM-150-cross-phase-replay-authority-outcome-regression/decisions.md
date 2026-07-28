# Decisions

- Use one Task Me task folder because SCRUM-150 is one bounded integration
  regression, not four independently deliverable implementation tasks.
- Add a composite validator rather than widening the existing P5 validator,
  which is intentionally scoped to the SCRUM-122–126 P5 chain.
- Treat old SCRUM-146 dependency evidence as stale after the exact 149 merge
  rebaseline; preserve it for drift detection and do not rewrite it as current.
- Keep Jira, Slack and Notion as projections. Only GWC artifacts and exact
  repository/CI observations can support gate decisions.
- Stop before G4. The user's FastLane request does not grant merge, deploy or
  production authority.
