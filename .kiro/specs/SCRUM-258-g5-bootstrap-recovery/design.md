# SCRUM-258 Design — Extend Existing G4/G5 Workflow

## Decision
Extend `.github/workflows/g4-g5-evidence.yml` with an `issue_comment` recovery job rather than introducing a parallel workflow.

## Recovery command
`APPROVE G5 RECOVERY <recovery_id> <owner/repo> <pr_number> <g4_approval_id> <scope_hash_16> <approved_head_sha> <merge_commit_sha> <validate_run_id> <build_run_id> <source_authority_sha256> <expires_at_utc>`

## Validation route
1. Confirm the comment belongs to a merged PR.
2. Confirm human permission is `write`, `maintain`, or `admin`.
3. Confirm expiry and immutable source-authority SHA-256 are valid.
4. Resolve the exact PR head and merge commit and require full-SHA equality.
5. Read immutable merge metadata for the recorded original G4 approval identifier and approved head.
6. Resolve the two supplied required workflow run IDs and require `push:main`, exact merge SHA, terminal `success`, and the expected workflow identities.
7. Reject an existing conflicting recovery marker; return idempotent success for a fully materialized exact duplicate.
8. Validate and upload recovery authority and G5 evidence artifacts.
9. Upsert sanitized `gwc:g5-recovery-authority`, recovered `gwc:g4-merge-proof`, and recovered `gwc:g5-status` traces carrying recovery provenance.

## Compatibility
Normal event-driven authority, merge proof and G5 status jobs remain unchanged. Recovery is a distinct provenance mode and cannot be used for an open or unmerged PR.
