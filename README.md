
# Instruction Governance

Central Git-based control plane for project instructions, governance policies,
agent contracts, project profiles, release packages, rollout verification, and
rollback evidence.

This repository is designed to be copied into:

```text
https://github.com/nhatnguyenquang1838-coder/gwc
```

## Core model

```text
Central repository = source of truth
Project repository = pinned consumer
InstructionOps Agent = Git orchestrator
Pull Request = review boundary
Manifest and SHA-256 = integrity boundary
Approval envelope = authority boundary
```

## What is included

- Canonical coding governance policy.
- E2E Draft PR delivery workflow.
- Local-agent and copyable-command rules.
- Project packages for DS MCP, Rental Home, and PM Skills.
- InstructionOps Agent and coding-agent bootstrap contracts.
- JSON Schemas.
- Validation, package-build, semantic-diff, and rollout-verification tools.
- GitHub Actions for validation, package builds, and manual release publication.
- Release manifest and changelog.

## Safety defaults

- The canonical core policy is pinned to version `1.0`.
- Canonical SHA-256:

```text
04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1
```

- Repository writes require an active verified Project Profile with
  `write_enabled: true`.
- `rental-home` and `pm-skills` are intentionally fail-closed until their
  repository identity and protected-base governance are verified.
- Instruction deletion uses lifecycle transitions:
  `active -> deprecated -> disabled -> archived`.
- Production changes, deployment, merge, credential operations, and
  production-data access require separate authority gates.
- The repository contains no credentials.

## Quick start

### 1. Copy to the `gwc` repository

Copy the contents of this directory to the root of a local checkout of `gwc`.

PowerShell:

```powershell
Copy-Item -Recurse -Force .\instruction-governance\* C:\path\to\gwc\
```

Bash:

```bash
cp -a instruction-governance/. /path/to/gwc/
```

### 2. Install validation dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Validate everything

```bash
python tools/validate_instructions.py
```

### 4. Build a project package

```bash
python tools/build_project_package.py ds-mcp --output dist
```

Output:

```text
dist/ds-mcp/<version>/
├── .governance/
└── package-manifest.yaml
```

### 5. Compare package revisions

```bash
python tools/diff_instruction_package.py \
  dist-old/ds-mcp/1.0.0 \
  dist/ds-mcp/1.1.0
```

### 6. Verify a rollout checkout

```bash
python tools/verify_rollout.py \
  dist/ds-mcp/1.1.0 \
  /path/to/ds_mcp_server
```

## Instruction CRUD commands

The InstructionOps Agent accepts these normalized commands:

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

All modifying commands produce a proposal, scoped approval envelope, dedicated
branch, validation evidence, and Draft PR. They never imply merge or deployment.

## Project activation

A project becomes write-capable only after:

1. Repository owner and name are verified.
2. Default and protected branches are verified.
3. Connector identity is verified.
4. Protected-base governance is read.
5. `write_enabled` is deliberately changed to `true`.
6. The profile change is reviewed through a Pull Request.

## Git workflow

Recommended branch prefixes:

```text
docs/
chore/
feature/
fix/
ai/
```

Never push instruction changes directly to a protected branch.

## Release model

Project packages use Semantic Versioning:

- `PATCH`: wording or typo changes that do not alter behavior.
- `MINOR`: additive rule, check, command, or gate.
- `MAJOR`: breaking workflow, authority, schema, or compatibility change.

Projects pin a package version and source commit. They must not consume
`latest` automatically.

## Approval command format

Any exact user command must be displayed as a standalone copyable block:

```text
APPROVE CP-20260712-001 0123456789abcdef
```

`APPROVE G2_EXECUTION` is not a valid execution token.

## Current project status

| Project | Status | Write enabled |
|---|---:|---:|
| `ds-mcp` | active | yes |
| `rental-home` | pending verification | no |
| `pm-skills` | pending repository assignment | no |

## No implicit production action

Building or publishing an instruction package does not:

- merge a Pull Request;
- deploy an application;
- change Vercel configuration;
- rotate credentials;
- run migrations;
- read or write production data.
