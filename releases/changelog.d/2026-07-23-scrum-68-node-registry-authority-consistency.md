## SCRUM-68 node registry authority consistency repair

### Fixed

- Align all `sync_projection` descriptors with the global runtime registry invariant by setting `authority_boundary: read_only` while retaining G2/G3 applicability metadata.
- Align the `scale_control.workflow-run-observability` and `scale_control.rollout-progress-projection` audit projections with the same read-only authority rule.
- Update family validators and focused tests so audit projections cannot grant G2, G3, G5, or other gate authority.
- Add an executable regression test that compiles and validates the complete 81-node catalog.

### Preserved

- Exactly 81 unique descriptors across nine families.
- `package_version: 1.16.0`.
- `scale_81_nodes_allowed: false`.
- No runtime engine, executable failure-proof implementation, merge, deploy, release, production configuration/data, credential, secret, or migration authority.
