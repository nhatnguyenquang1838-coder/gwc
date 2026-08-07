# SCRUM-272 — Standing autonomous pre-prod authority policy

- Add the bounded `AUTONOMOUS_PREPROD_INTEGRATION_POLICY` contract and active policy profile.
- Add closed schemas for parent run policy, run manifest, and exact-head standing G4 receipts.
- Add deterministic, data-only policy validation plus child G2 and standing G4 authority derivation.
- Preserve legacy human G4 compatibility while allowing an autonomous `pre-prod` standing receipt as the authority source; current PR-evidence binding remains mandatory.
- Fail closed on `main`, R3 child scope, unallowlisted tasks/actions, protected control-plane self-modification, stale base/head/body/graph/story/evidence, expiry, and policy/manifest drift.
- No deploy, release, runtime reload, production data/configuration, credential, secret, migration, branch-protection, or live merge authority is introduced by this change.
