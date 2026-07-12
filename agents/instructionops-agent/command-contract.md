
# InstructionOps Command Contract

## Syntax

```text
INSTRUCTION LIST [project-id]
INSTRUCTION GET <project-id> [instruction-id]
INSTRUCTION CREATE <project-id> <instruction-id>
INSTRUCTION UPDATE <project-id> <instruction-id>
INSTRUCTION DEPRECATE <project-id> <instruction-id>
INSTRUCTION VALIDATE [project-id]
INSTRUCTION BUILD <project-id>
INSTRUCTION DIFF <project-id> <from-version> <to-version>
INSTRUCTION PUBLISH <project-id> <version>
INSTRUCTION ROLLBACK <project-id> <version>
INSTRUCTION DRIFT <project-id>
```

## Read operations

`LIST`, `GET`, `VALIDATE`, and `DRIFT` are read-only unless a separate command
explicitly requests remediation.

## Modifying operations

`CREATE`, `UPDATE`, `DEPRECATE`, `PUBLISH`, `ROLLBACK`, and rollout remediation
must produce:

- inspection evidence;
- written proposal;
- affected consumers;
- semantic version decision;
- change plan;
- visual package;
- approval envelope;
- exact approval token;
- validation plan;
- rollback plan.

## Output contract

Every response includes:

- project;
- package version;
- source files;
- target repositories;
- risk;
- authority gate;
- authorized actions;
- excluded actions;
- drift status;
- next exact user command when one is required.

## Errors

```text
INSTRUCTION_NOT_FOUND
INSTRUCTION_ALREADY_EXISTS
INSTRUCTION_ID_INVALID
INSTRUCTION_REFERENCED
PROJECT_NOT_FOUND
PROJECT_PROFILE_INVALID
PACKAGE_SCHEMA_INVALID
PACKAGE_HASH_MISMATCH
PACKAGE_BUILD_FAILED
ROLLOUT_TARGET_INVALID
INSTRUCTION_DRIFT_DETECTED
APPROVAL_TOKEN_INVALID
APPROVAL_EXPIRED
SCOPE_DRIFT
```
