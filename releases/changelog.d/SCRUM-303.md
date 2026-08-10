SCRUM-303 upgrades `intake_context.files-read-scope` to a deterministic bounded read-scope runtime contract with explicit exclusion/missing evidence, repository/UA drift invalidation, stable scope hashing, runtime binding, and authority-negative coverage.

Validation rebinds the delivery against the current descendant `pre-prod` target while preserving the lane authority anchor and fail-closed machine-policy ceiling. Trusted parent authority is resolved from the bot-authored lane manifest/receipt rather than from the route marker alone.
