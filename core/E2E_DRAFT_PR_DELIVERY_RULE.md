# E2E Draft PR Delivery Rule

## Purpose

Allow the agent to complete an approved coding task end-to-end and deliver a validated Draft Pull Request for final user review.

The user reviews the final result through the Pull Request.

This mode never authorizes merge, deployment, production configuration, credential changes, migrations, or production-data operations.

## Activation

This mode is activated only when the user explicitly states:

`DELIVER_E2E_PR`

The activation phrase alone is not execution approval.

The agent must still perform policy boot, read-only inspection, proposal generation, visual review, approval-envelope generation, and exact approval-token validation.

## End-to-end workflow

When `DELIVER_E2E_PR` is active, the agent must execute this workflow:

```text
Policy boot
→ Read-only inspection
→ Proposal and visual package
→ Exact scoped approval
→ Dedicated branch/worktree
→ Implementation
→ Local validation
→ Full diff review
→ Push approved branch
→ Create or update Draft PR
→ Monitor CI
→ Repair repository-fixable CI failures
→ Deliver final PR report
→ STOP
```

## Single approval envelope

The proposal should use one `G2_EXECUTION` approval envelope containing only the actions needed to deliver a Draft PR:

```yaml
authority_gate: G2_EXECUTION

authorized_actions:
  - modify_approved_files
  - run_sandboxed_validation
  - push_working_branch
  - open_or_update_draft_pr

excluded_actions:
  - merge
  - auto_merge
  - deploy
  - release
  - production_data_write
  - production_config_change
  - credential_rotation
  - destructive_migration
```

The exact approval format remains:

`APPROVE <approval_id> <first-16-characters-of-scope_hash>`

Generic responses such as `OK`, `Approved`, `Proceed`, or `Do it` are not execution approval.

## Approval scope

The approval envelope must bind the work to:

- Active Project Profile.
- Repository.
- Base ref and full base SHA.
- Dedicated working branch.
- Approved files or modules.
- Risk class.
- Authorized actions.
- Excluded actions.
- Change-plan hash.
- Mermaid hash.
- SVG hash.
- PNG hash.
- Expiry time.
- Canonical scope hash.

The agent must not begin implementation until the exact token is received.

## Autonomous execution boundary

After valid approval, the agent may proceed without requesting confirmation for every normal implementation step, provided all actions remain within the approved envelope.

Allowed autonomous actions:

- Create the approved dedicated branch or worktree.
- Modify only approved files or modules.
- Add or update tests within approved scope.
- Run inspected and approved validation commands.
- Commit changes to the working branch.
- Push the approved working branch.
- Create or update a Draft PR.
- Update the Draft PR description.
- Monitor CI for the current PR head SHA.
- Diagnose repository-fixable CI failures.
- Apply fixes within the approved scope.
- Push repaired commits.
- Repeat the bounded CI loop.

The agent must provide concise progress updates but does not need additional approval for each permitted action.

## Mandatory stop conditions

The agent must stop and request a new approval envelope when any of the following occurs:

- Base SHA changes.
- Another actor changes the working branch.
- Target files or modules change materially.
- A new dependency is required but was not approved.
- Database schema or migration becomes necessary unexpectedly.
- Authentication, authorization, security, architecture, public API, or data behavior changes beyond the proposal.
- Deployment or production configuration becomes necessary.
- Production-data access or mutation becomes necessary.
- The fix requires touching an excluded component.
- Visual artifacts no longer represent the implementation scope.
- The approval expires.
- The CI repair budget is exhausted.
- The repository identity or active profile becomes inconsistent.

The agent must produce a scope delta, regenerate the approval artifacts, and request a new exact approval token.

## Branch and commit rules

The agent must:

- Use one dedicated branch and isolated worktree/session.
- Never push directly to the default or protected branch.
- Never force-push.
- Never rewrite shared history.
- Never delete branches.
- Never change the PR base.
- Never enable auto-merge.
- Verify repository, branch, expected head SHA, and target file state before every write.
- Keep commits bounded to the approved task.
- Exclude unrelated cleanup, dependency upgrades, formatting sweeps, and opportunistic refactors.

## Validation requirements

Before creating or updating the Draft PR, the agent must:

1. Inspect every command, script, hook, plugin, and lifecycle action before execution.
2. Run applicable typecheck, lint, tests, build, contract checks, and UI smoke checks.
3. Review the complete diff against the approved base SHA.
4. Check for:
   - Secrets.
   - Unrelated files.
   - Accidental deletion.
   - Generated noise.
   - Unexpected lockfile changes.
   - Weakened tests.
   - Modified CI behavior.
   - Missing documentation.
5. Record sanitized commands and results.

A failed or skipped validation must be reported honestly.

## Draft PR requirements

The agent must create a Draft PR containing:

- Objective.
- Approval ID and scope-hash prefix.
- Base SHA and current PR head SHA.
- Approved scope.
- Files and modules changed.
- Main implementation decisions.
- API, UI, data, workflow, security, and infrastructure impact.
- Tests and validation results.
- Visual artifacts or links.
- Migration and configuration status.
- Known risks.
- Rollback approach.
- Explicit exclusions.
- Statement that merge, deployment, and production operations are not authorized.

## CI monitoring

After every push to the PR branch:

1. Schedule or perform a CI check after `+2 minutes`.
2. Verify the workflow belongs to the current PR head SHA.
3. Verify all required checks exist.
4. Verify all required checks complete successfully.
5. Reject stale, unrelated, skipped, neutral, cancelled, timed-out, or weakened evidence.

For pending states:

- Make no code change.
- Continue monitoring the same SHA.

For repository-fixable failures:

1. Identify the workflow, job, step, and root cause.
2. Fix only within the approved scope.
3. Run applicable local validation.
4. Push using expected-SHA guards.
5. Record the new head SHA.
6. Restart CI monitoring.

Repair limits:

- Maximum three automatic repair attempts.
- Maximum one repeated attempt for the same unchanged root cause.

After the repair budget is exhausted, stop and report the blocker.

## Completion condition

The task is complete only when:

- The Draft PR exists.
- PR head SHA matches the latest pushed commit.
- Required CI is green for that SHA.
- Required validation evidence is recorded.
- Full diff review is complete.
- Documentation is current.
- No material scope drift occurred.
- No excluded authority was exercised.

## Final response

The final response must lead with:

```text
E2E PR DELIVERY COMPLETE
```

Then report:

- Project profile.
- Repository.
- Branch.
- Draft PR URL and number.
- Approval ID and scope-hash prefix.
- Base SHA.
- Final head SHA.
- Files changed.
- Behavior changed.
- Tests added or updated.
- Local validation results.
- CI workflow, run, and required-check results.
- Visual artifact hashes.
- Unperformed checks and reasons.
- Residual risks.
- Recommended user review focus.

End with:

`Not merged. Not deployed. No production-data operation performed.`

After delivering the final report, stop and wait for the user to review the Pull Request.

## Prohibited behavior

Even in E2E mode, the agent must never:

- Merge or enable auto-merge.
- Deploy or publish a release.
- Modify production configuration.
- Rotate credentials.
- Run production migrations.
- Read or write production data.
- Expand scope silently.
- Use stale CI evidence.
- Claim success without matching evidence.
