# G5 Standing Automation Policy v1.0

## Status

- Document ID: `g5-standing-automation-policy`
- Version: `1.0`
- Lifecycle: `active`
- Scope: `nhatnguyenquang1838-coder/gwc`
- Related work: `SCRUM-143`, `SCRUM-151`

## Purpose

GWC intentionally keeps `G4_MERGE`, `G5_DEPLOY`, and `G6_PRODUCTION_DATA`
as separate authority gates. This file declares the narrow exception that is
already part of the repository's protected-base operating model: publishing the
GWC Power package after a protected `main` update is standing automated G5
behavior, not an ad hoc manual deploy.

## Standing automated G5 behavior

When `.github/workflows/publish-power.yml` runs on `push` to `main`, it may
validate, package, publish a GitHub Release, and update the `power-dist` branch
for the exact `main` commit that triggered the workflow.

This behavior is allowed only while all of these constraints remain true:

1. The workflow is committed in the protected repository and triggered by the
   protected `main` branch or explicit `workflow_dispatch`.
2. The reusable publisher is pinned to an exact DW-SuperApps foundation SHA.
3. The publication target remains the GWC Power distribution and the
   `power-dist` branch.
4. The workflow does not read or write production data.
5. The workflow does not rotate credentials, change production configuration,
   run migrations, reload runtime services, or perform destructive operations.
6. The workflow produces auditable GitHub evidence for the exact source SHA.

Changing the trigger, target distribution branch, foundation reference, release
semantics, credential model, or production boundary is outside this standing
authorization and requires fresh governed review.

## Manual dispatch behavior

`workflow_dispatch` remains supported. Its `publish_release` and
`publish_distribution_branch` inputs are explicit operator controls. Leaving
those inputs false must not publish a release or update the distribution branch.

## Required audit evidence

Each standing automated G5 run should be auditable from GitHub evidence:

- triggering event;
- triggering `main` SHA;
- workflow run ID and job ID;
- package version;
- artifact name and digest when emitted;
- release tag or release URL when emitted;
- `power-dist` branch SHA when updated;
- final workflow conclusion.

If the required evidence cannot be read back, the correct status is not "G5
PASS"; it is an unavailable or incomplete evidence state.

## Boundary

This policy does not grant merge authority, deploy authority for other systems,
production-data authority, credential authority, or permission to bypass
exact-head G4 approval. It only documents the existing standing publication
automation for the GWC Power distribution.
