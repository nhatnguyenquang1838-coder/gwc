# SCRUM-264 — PR-native G4 authority receipt guard

## Changed

- Extended `schemas/gate-action-authority.schema.json` so `G4_MERGE` / `merge_approved_pr` action packets must carry `evidence_readback.g4_authority_receipt`.
- Extended `tools/validate_gate_action.py` to fail closed unless the G4 merge packet includes a trusted `github-actions[bot]` `gwc:g4-authority-receipt` bound to the current PR head.
- Added CLI options for expected G4 approval ID and scope prefix checks.
- Expanded regression tests for missing, stale, expired, head-mismatched, and scope-mismatched G4 authority receipts.

## Boundary

This change hardens pre-merge validation only. It does not grant merge, deploy, release, production data/configuration, credential, migration, or G6 authority.
