# SCRUM-261 — Gate-node runtime binding hotfix

- Repair the merged PR #173 intake-card regression while preserving fail-closed
  behavior and stable redaction/reason-code contracts.
- Add a revision-bound, provider-neutral Gate–Node route profile, schemas, and
  deterministic resolver.
- Require G2 repository writes to resolve through
  `repo_delivery.scoped-file-write`, continue through exact diff readback, and
  identify the G3 human boundary without granting G3 authority.
- Add focused regression tests and ChatGPT runtime instructions.

No merge, deployment, release, production configuration/data, credential,
secret, migration, package export, or G4/G5/G6 authority is introduced.
