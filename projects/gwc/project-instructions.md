# GWC Project Instructions

## Identity

- Project ID: `gwc`
- Repository: `nhatnguyenquang1838-coder/gwc`
- Runtime agent: `DWC`
- Work-tracking source of truth: DS Admin

## Default workflow

```text
G0 intake
→ automatic G1 inspection
→ bounded plan
→ automatic G2 execution for non-risk work
→ validation and full diff review
→ automatic G3 Draft PR
→ user review after CI
→ separate G4 merge decision
→ separate G5 deploy decision
→ separate G6 production decision
```

## DWC repository access

DWC may read the complete verified repository and may create or update any file
required by the active DS Admin task on a dedicated guarded branch.

Repository access is task-bounded rather than path-bounded. DWC must not use
this permission for unrelated cleanup, broad refactoring, dependency changes,
formatting sweeps, or opportunistic edits.

## Human direction boundary

Explicit user direction is required before DWC executes a change involving:

- financial impact;
- architecture change;
- security boundary change;
- production configuration;
- credentials or secrets;
- production data;
- destructive or irreversible behavior;
- broad blast radius.

An explicit user request to create the PR grants branch, implementation,
validation, push, and Draft PR authority for the stated scope only.

## Validation

Before Draft PR creation DWC must:

- parse and validate changed YAML and JSON;
- run applicable repository validation;
- review the full diff against the protected base;
- check for secrets, accidental deletion, generated noise, weakened tests, and
  scope drift;
- record limitations honestly when a validation cannot be executed locally.

## Permanent exclusions

DWC must never automatically push to `main`, merge, auto-merge, deploy, publish
a release, change production configuration, rotate credentials, access
production data, force-push, delete branches, or rewrite shared history.
