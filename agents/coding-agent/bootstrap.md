
# Coding Agent Bootstrap

At the start of every coding, repository, PR, deployment, configuration,
migration, or production-data task:

1. Locate the project package manifest.
2. Verify every package file hash.
3. Read:
   - canonical core policy;
   - active Project Profile;
   - project extension;
   - E2E delivery rule;
   - project instructions;
   - additional required instructions in the package manifest.
4. Verify exactly one profile is active.
5. Verify repository owner, name, default branch, protected branches,
   connector, identity, and `write_enabled`.
6. State:
   - policy version and SHA;
   - active profile;
   - repository;
   - risk;
   - required gate;
   - authorized actions;
   - excluded actions.
7. Stop with `INSTRUCTION_PACKAGE_INVALID` on missing, altered, conflicting, or
   unverified files.
8. Do not retrieve or execute a newer instruction package automatically.
9. Instruction updates arrive only through an approved Git Pull Request.

When `claim_required_for_e2e` is true, do not create a branch or modify the
repository until the approved work item is successfully claimed and ownership
and lease are verified.
