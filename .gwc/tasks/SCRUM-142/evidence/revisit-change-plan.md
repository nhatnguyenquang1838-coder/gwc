# SCRUM-142 R2 Change Plan

## Base

- Repository: `nhatnguyenquang1838-coder/gwc`
- Protected base: `main@c855336dc17f20115e640516107999b08e9d783e`
- Working branch: `repair/scrum-142-canonical-ua-refresh-r2-20260726`
- Scope hash: `sha256:fccfa84b02f6e178b4d14342759c7eebc5149f7c7ece4b5df3808f6cdee8620b`

## Ordered execution

1. Re-read current base and invalidate this envelope on drift.
2. Create the guarded repair branch from the exact base.
3. Run Understand-Anything `/understand --full --language en` in a trusted local checkout.
4. Verify `.ua/knowledge-graph.json` and `.ua/meta.json` bind to the exact base and include SCRUM-105 durable runtime surfaces.
5. Replace the five invalid G0/G1 files with the validated canonical packet.
6. Persist the new G2 envelope, approval envelope, review report, UA report and projections.
7. Run G0/G1 validation, graph JSON validation, diff scope validation and repository-safe tests.
8. Commit and push only the approved branch. Stop before Draft PR creation.

## Invalidators

- main SHA changes
- file or action scope changes
- scope hash changes
- approval expires
- UA output is not bound to the approved base
- any out-of-scope runtime, validator, workflow or package change appears
