## SCRUM-68 node registry authority consistency repair

### Fixed

- Align all `sync_projection` descriptors with the global runtime registry invariant by setting `authority_boundary: read_only` while retaining G2/G3 applicability metadata.
- Align the `scale_control.workflow-run-observability` and `scale_control.rollout-progress-projection` audit projections with the same read-only authority rule.
- Add the explicit `g3_required` runtime-node authority value and map it to `G3_PR` in the global registry validator.
- Migrate all nine `validation_quality` descriptors and five non-projection `scale_control` G3 descriptors from the contradictory `g2_required + G3_PR` mapping to `g3_required + G3_PR`.
- Update family validators and focused tests so G3-only nodes cannot imply G2 execution authority and audit projections cannot grant gate authority.
- Keep the executable regression test that compiles and validates the complete 81-node catalog.

### Preserved

- Exactly 81 unique descriptors across nine families.
- `package_version: 1.16.0`.
- `scale_81_nodes_allowed: false`.
- No runtime engine, executable failure-proof implementation, merge, deploy, release, production configuration/data, credential, secret, or migration authority.
