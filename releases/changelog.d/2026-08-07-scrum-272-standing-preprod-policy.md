# SCRUM-272 — Standing autonomous pre-prod authority policy

- Add the bounded `AUTONOMOUS_PREPROD_INTEGRATION_POLICY` contract and active policy profile.
- Add closed schemas for parent run policy, approved run manifest, and exact-head standing G4 decision receipts.
- Require a trusted `github-actions[bot]` parent-run authority receipt that binds approval ID, immutable manifest approval-scope digest, policy revision/digest, scope prefix and expiry.
- Add deterministic child G2 and standing G4 derivation with parent-approval provenance and replay-stable digests; both ALLOW outputs are explicitly contract-only with `trust_state=requires_trusted_repo_ci_projection` until a later trusted runtime integration projects them from repository evidence.
- Cover the complete bounded G2 lifecycle action set: guarded branch/worktree, approved edits, sandbox validation, stage, commit and branch push; child request risk must exactly match the manifest-approved task risk.
- Require canonical repository-relative POSIX scope paths before control-plane overlap checks; reject absolute/root aliases, dot traversal, backslashes and glob metacharacters.
- Keep live `gate-action-authority` validation byte-compatible with `main`; standing G4 decisions do not replace the existing trusted human G4 receipt in this task.
- Preserve the SCRUM-271 runtime contract verbatim and append only the SCRUM-272 standing-policy extension boundary; protect the evidence-runtime contract, schemas, tools and workflow from child self-modification.
- Fail closed on `main`, R3 child scope, risk downgrade/upgrade, unallowlisted tasks/actions, forged/stale parent authority, protected control-plane self-modification, stale base/head/body/graph/story/evidence, expiry and policy/manifest drift.
- No merge, deploy, release, runtime reload, production data/configuration, credential, secret, migration, branch-protection, or live standing-authority issuance is introduced by this change.
