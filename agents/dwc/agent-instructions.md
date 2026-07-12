# DWC Repository Operations Contract

## Scope

This contract applies to the DWC runtime operating on
`nhatnguyenquang1838-coder/gwc` through the verified `DWC` connector.

It records repository permissions granted by higher-priority platform and
project runtime instructions. It does not independently weaken the canonical
core policy for other agents or repositories.

## Mission

Allow DWC to inspect, maintain, validate, and deliver bounded changes to this
repository through a guarded branch and Draft Pull Request without repeated
approval prompts for routine repository operations.

## Automatic inspection — G0/G1

DWC may automatically perform read-only operations needed to understand a task:

- inspect repository metadata, branches, tree, files, binary artifacts, PRs,
  workflow runs, and workflow artifacts;
- read governance and project context from the protected base;
- compare refs, hashes, package versions, consumers, and CI evidence;
- create or update the matching DS Admin task record.

Read-only inspection does not authorize writes, merge, deployment, or
production access.

## Automatic bounded execution — G2

DWC may automatically execute a bounded, non-risk repository change when all
of the following are true:

- the user has requested the outcome;
- repository identity and protected base are verified;
- exactly one DS Admin task represents the work;
- the scope is explicit and limited to the requested result;
- a dedicated allowed-prefix branch is used;
- no protected branch is written directly;
- no secret, production configuration, production data, destructive action,
  financial impact, architecture change, security-boundary change, or broad
  blast radius is introduced;
- validation and complete diff review are performed before Draft PR creation.

Within that boundary DWC may create the branch, create or update any repository
file required by the task, add tests and documentation, push commits, inspect
CI, repair repository-fixable CI failures, and update the same Draft PR.

## Draft PR delivery — G3

After validation, DWC may automatically create or update a Draft Pull Request
for bounded non-risk work. The PR is the user review boundary.

Explicit human direction is required before G2/G3 execution when the task has
any of these characteristics:

- financial impact;
- architecture change;
- security-boundary change;
- production configuration;
- credential or secret change;
- production data access;
- destructive or irreversible action;
- broad blast radius.

A user request that explicitly asks DWC to create the bounded PR for one of
these categories satisfies the human-direction requirement only for branch,
implementation, validation, push, and Draft PR creation. It does not grant
merge, deploy, release, or production authority.

## Permanent exclusions

DWC must not automatically:

- push directly to `main` or another protected branch;
- merge, enable auto-merge, close another actor's PR, or change a PR base;
- force-push, delete branches, or rewrite shared history;
- deploy, publish a release, or modify production configuration;
- create, expose, rotate, or commit credentials and secrets;
- read or write production data;
- perform destructive migrations or irreversible operations.

G4 merge, G5 deploy, and G6 production operations always require a separate
human decision.

## Completion evidence

A DWC repository task is complete only when the Draft PR exists, the latest
head SHA is known, applicable validation is recorded, CI state is reported,
and exclusions and residual risks are stated accurately.
