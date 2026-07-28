# SCRUM-150

Implement a small, fail-closed cross-phase evidence validator and focused
fixtures/tests. The validator consumes observed records; it must not execute
providers, mutate checkpoints, write projections, approve gates, promote a
candidate, or infer missing evidence.

The prior SCRUM-146 evidence files are useful source observations but are bound
to an older base. Their stale binding must be rejected or explicitly classified
until current exact evidence is supplied.
