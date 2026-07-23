## SCRUM-75 G5 CI verification and runtime catalog KG normalization

### Added

- `core/G5_CI_VERIFICATION_CONTRACT_v1.0.md` for exact merge-SHA GitHub Actions run resolution, fallback routing, checkpointing, and G5 evidence classification.
- `core/RUNTIME_CATALOG_KNOWLEDGE_GRAPH_CONTRACT_v1.0.md` to standardize Gate, Capability Family, Runtime Node, Edge Scenario, and Artifact terminology.
- G5 CI evidence and checkpoint schemas.
- Runtime catalog taxonomy and knowledge-graph projection schemas.
- Validators and tests for no-false-pass G5 CI evidence and 81-node catalog taxonomy preservation.
- DWC capability declaration for automatic read-only `g5_ci_status_verify`.

### Changed

- Instruction source registry now publishes the G5 CI verification and runtime catalog KG contracts.

### Safety

- Read-only G5 status verification only.
- No new merge, auto-merge, deploy, release, publish, runtime reload, production configuration/data, credential, secret, migration, force-push, branch deletion, shared-history rewrite, or PR base-change authority.
- The 81 Runtime Node count is preserved; no tenth family or eighty-second node is introduced.
