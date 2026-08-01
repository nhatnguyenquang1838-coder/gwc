# SCRUM-258 Requirements — Authorized G5 Bootstrap Recovery

## Objective
Provide a fail-closed recovery path for merged PRs whose canonical G4/G5 event chain could not execute because the evidence workflow was introduced by that same merge.

## Functional requirements
1. Accept recovery authority only from an exact human PR comment on an already merged PR.
2. Bind authority to recovery ID, repository, PR number, original G4 approval ID, scope-hash prefix, exact approved head SHA, exact merge commit SHA, exact required workflow run IDs, immutable source-authority SHA-256, and expiry.
3. Verify approver permission, merged PR state, exact head/merge SHAs, original G4 provenance, immutable source-authority digest, and exact successful required workflow runs.
4. Verify bootstrap provenance using immutable PR/merge metadata and the recorded original G4 approval identifier.
5. Produce canonical Actions artifacts and sanitized PR traces with `recovery_mode=bootstrap_manual_authority`.
6. Be idempotent and reject duplicate, conflicting, expired, unauthorized or mismatched requests.
7. Never commit evidence to main or create a recursive evidence PR.

## Non-functional requirements
- Preserve existing normal G4/G5 event behavior.
- Preserve exactly 81 runtime nodes.
- Fail closed.
- No deploy, release, publish, runtime reload, production configuration/data, secrets or migrations.
