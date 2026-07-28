# Coding guide

- Reuse `resolve_g5_status.py`, `validate_g5_status.py`,
  `validate_github_g5_g6_jira_projection.py`, and
  `hash_integrity_artifacts.py`.
- Keep exact SHA equality checks strict; reject stale PR head, merge/main
  mismatch, missing exact-SHA CI, and projection authority leakage.
- Do not invent the new manifest path. Verify it against the protected-base
  package/evidence conventions before adding it; path discovery is part of the
  approved bounded scope.
