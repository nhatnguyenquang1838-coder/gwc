
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
- Global agent behavior and adaptive response presentation contracts.
- Agent-readable G0, G1, and G2 phase skills with a bounded G1-to-G2 handoff.
- E2E Draft PR delivery workflow.
- Local-agent and copyable-command rules.
- Project packages for GWC, DS MCP, Rental Home, and PM Skills.
- DWC runtime, InstructionOps Agent, and coding-agent bootstrap contracts.
- JSON Schemas, including versioned G0/G1 lifecycle artifact contracts.
- Deterministic G0/G1 gate validation, package-build, semantic-diff, and rollout-verification tools.
- GitHub Actions for validation, package builds, and manual release publication.
- Release manifest and changelog.

## Agent operating model

GWC package `1.6.0` retains the two modular operational contracts and adds an
agent-readable G2 handoff skill without changing the canonical core hash or
replacing the existing G0/G1 lifecycle:

- `core/Agent_Behavior_Semantic_Contract_v1.0.md`;
- `core/Agent_Response_Presentation_Contract_v1.0.md`;
- `skills/gwc-g0/SKILL.md`;
- `skills/gwc-g1/SKILL.md`;
- `skills/gwc-g2/SKILL.md`.

The default reasoning flow is:

```text
Understand
→ Inspect
→ Reconstruct current context
→ Identify existing mechanisms
→ Accept a G1 decision
→ Verify the G1-to-G2 handoff
→ Integrate the smallest compatible improvement
→ Execute only when authorized
→ Validate and report evidence
```

Agents prefer `Reuse → Extend → Refactor → Replace`. Missing task, connector,
or persistence evidence degrades the workflow to verified read-only or
planning-only mode instead of blocking all useful analysis. Repository mutation
and authority escalation still fail closed.

G2 uses a concise execution brief rather than inventing a parallel canonical
artifact. Temporary session context may be discarded, the active handoff is
superseded when evidence changes, and only material decisions, scope/authority
changes, final repository evidence, validation, rollback, residual risks, and
the next gate are promoted to existing durable channels such as DS Admin, Git,
or Pull Request history.

Responses use direct Markdown by default, tables for comparison, Mermaid for
workflow or architecture relationships, and SVG/PNG only when requested,
required, or materially useful. Stricter project and approval artifact rules
continue to apply.

## Safety defaults

- The canonical core policy is pinned to version `1.0`.
- Canonical SHA-256:

```text
04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1
```

- Repository writes require an active verified Project Profile with
  `write_enabled: true`.
- On this repository, DWC read-only inspection is automatic; bounded non-risk
  branch writes and Draft PR delivery are automatic under the active `gwc`
  profile and one DS Admin task.
- Financial, architecture, security-boundary, production configuration,
  credential, production-data, destructive, irreversible, and broad-blast-
  radius changes require explicit human direction.
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

### 4. Validate G0/G1 lifecycle artifacts and prepare G2

```bash
python tools/validate_g01.py --workspace .gwc
python -m unittest tests.test_g01_lifecycle
```

The validator returns `PASS` only when G0 context and all G1 intake, preflight,
options, and decision artifacts are schema-valid and mutually consistent. A G1
`PASS` is evidence for G2 planning only. `skills/gwc-g2/SKILL.md` then re-checks
freshness, task traceability, scope, risk, runtime authority, and exclusions
before bounded execution. Neither phase grants merge, deployment, release, or
production authority. See `docs/g01-lifecycle.md`.

### 5. Build a project package

```bash
python tools/build_project_package.py ds-mcp --output dist
```

Output:

```text
dist/ds-mcp/<version>/
├── .governance/
└── package-manifest.yaml
```

### 6. Compare package revisions

```bash
python tools/diff_instruction_package.py \
  dist-old/ds-mcp/1.0.0 \
  dist/ds-mcp/1.1.0
```

### 7. Verify a rollout checkout

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

## DWC repository operations

For `nhatnguyenquang1838-coder/gwc`, DWC is not restricted to a fixed file
allowlist. It may read the complete verified repository and modify any file
required by the active DS Admin task on a dedicated guarded branch.

The automatic path is:

```text
G0 current context
→ automatic G1 inspection and accepted decision
→ G2 handoff freshness and authority verification
→ automatic G2 bounded non-risk execution
→ validation and diff review
→ automatic G3 Draft PR
→ user review
```

Direct pushes to `main`, merge, auto-merge, deployment, release, production
configuration, credential operations, production data, force-push, branch
deletion, and shared-history rewrite remain prohibited or separately gated.

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
| `gwc` | active | yes |
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
