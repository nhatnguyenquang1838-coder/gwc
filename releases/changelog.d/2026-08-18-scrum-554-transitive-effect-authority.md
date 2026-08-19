# SCRUM-554 — transitive gate authority

- Adds a versioned capability registry and machine-readable effect graph/profile schemas for gate actions.
- Closes authority over deterministic and potentially reachable conditional child effects, including independent cross-repository authority.
- Treats retention/delete as `DESTRUCTIVE`, distinct from ordinary `RELEASE_PUBLISH`.
- Adds digest-bound `NO_TRANSITIVE_MUTATION` and `BOUNDED_TRANSITIVE_EFFECTS` legacy compatibility profiles; trigger-capable actions without a valid graph/profile fail `EFFECT_GRAPH_REQUIRED`.
- Binds effect policy and execution evidence to exact repository/event/action/branch-or-PR/SHA/workflow/gate-node identity and rejects historical or drifted evidence.
