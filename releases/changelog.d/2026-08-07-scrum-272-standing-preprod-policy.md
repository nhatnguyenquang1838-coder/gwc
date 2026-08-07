# SCRUM-272 — Standing autonomous pre-prod authority policy

- Add the bounded `AUTONOMOUS_PREPROD_INTEGRATION_POLICY` contract and active policy profile.
- Add closed schemas for parent run policy, approved run manifest, and exact-head standing G4 decision receipts.
- Require a trusted `github-actions[bot]` parent-run authority receipt that binds approval ID, immutable manifest approval-scope digest, policy revision/digest, scope prefix and expiry.
- Add deterministic child G2 and standing G4 derivation with parent-approval provenance and replay-stable digests.
- Cover the complete bounded G2 lifecycle action set: guarded branch/worktree, approved edits, sandbox validation, stage, commit and branch push.
- Keep live `gate-action-authority` validation byte-compatible with `main`; standing G4 decisions are contract-only until a later trusted repo-CI projection/readback integration is implemented.
- Fail closed on `main`, R3 child scope, unallowlisted tasks/actions, forged/stale parent authority, protected control-plane self-modification, stale base/head/body/graph/story/evidence, expiry and policy/manifest drift.
- No merge, deploy, release, runtime reload, production data/configuration, credential, secret, migration, branch-protection, or live standing-authority issuance is introduced by this change.
