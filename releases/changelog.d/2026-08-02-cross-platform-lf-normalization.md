# Cross-platform LF normalization and SHA closure

- Define UTF-8 without BOM and LF as the canonical tracked-text representation.
- Expand `.gitattributes` and add `.editorconfig` for Linux, macOS, and Windows parity.
- Add a fail-fast line-ending validator and focused regression tests.
- Add three-runner SHA parity CI with an aggregate equality check.
- Require normalization before SHA calculation, manifest generation, package export, commit, and G3 evidence.
- Preserve historical `.gwc/tasks/**` evidence instead of mass-updating old hashes.
- Revalidate derived SHA and package metadata against current protected `main` after approved base drift repair.
- Normalize the newly merged G0 skill to canonical LF before recomputing derived integrity metadata.
