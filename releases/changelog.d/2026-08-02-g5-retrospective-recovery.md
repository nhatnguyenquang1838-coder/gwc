# G5 retrospective recovery evidence

- Adds a bounded retrospective G5 recovery validator for merged PRs whose normal G4 authority receipt was not materialized before merge.
- Adds an issue-comment workflow that accepts `RETROSPECTIVE G5 RECOVERY EVIDENCE` comments only when the PR is already merged and the recovery binds PR number, approved head, merge commit, failed post-merge run, and quoted original G4 approval.
- Emits a recovery receipt without minting normal G4 authority, inferring new merge authority, authorizing manual G5 action, or granting G6/deployment/release authority.
- Covers the policy with focused unit tests for valid recovery, unmerged PR rejection, head mismatch rejection, new-authority rejection, and approval-expired-before-merge rejection.
