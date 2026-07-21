# CONSUMER_PACKAGE_EXPORT_RULE v0.1

## Status

```text
Rule ID: CONSUMER_PACKAGE_EXPORT_RULE
Version: 0.1
Introduced by: REVAMP-GWC-006
Applies to: projects/gwc/package.yaml generated package delivery
```

## Purpose

Define how GWC exports a governed consumer package into a project-local `.governance/` tree without creating a parallel instruction process.

## Core principle

```text
Generated package = portable governance copy.
Canonical authority = protected-base GWC source + gate evidence.
```

A generated `.governance/` package is boot evidence for consumer projects. It never grants write, PR, merge, deploy, release, production configuration, credential, migration, or production-data authority.

## Existing mechanism

| Mechanism | Purpose |
|---|---|
| `projects/gwc/package.yaml` | Declares package source entries, targets, delivery mode, and write boundary |
| `schemas/project-package.schema.json` | Validates package shape and disallows undeclared fields |
| `tools/validate_instructions.py` | Validates package schema, safe paths, source existence, duplicate targets, and delivery write boundary |
| `docs/project-consumer-agent-instructions.md` | Defines generated `.governance/*` package boot behavior |

This rule extends those mechanisms. It does not replace them.

## Export entry model

Each package entry must come from the package `instructions` list:

```yaml
- id: <stable-kebab-id>
  path: <repo-relative-source-path>
  target: <consumer-relative-target-path>
  required: true|false
```

Rules:

```text
✅ source path must be repo-relative
✅ target path must be consumer-package-relative
✅ target must normally start with .governance/
✅ required=true missing source is fatal
✅ required=false missing source is skipped and recorded
❌ absolute paths forbidden
❌ parent traversal forbidden
❌ Windows backslash forbidden
❌ duplicate ids forbidden
❌ duplicate targets forbidden
```

## Export manifest

Every export run should produce:

```text
<output-root>/.package-export-manifest.json
```

The manifest records project id, package version, source repo/ref/SHA, target root, generation time, and one entry per copied or skipped package item.

## Determinism requirements

```text
✅ stable package input order
✅ stable JSON key order
✅ UTF-8 copy
✅ SHA-256 calculated from copied bytes
✅ deterministic manifest for same inputs
```

## Gate behavior

| Gate | Behavior |
|---|---|
| G0 | May read package/export rule and detect package availability |
| G1 | May propose package export/update scope |
| G2 | Required before changing package source, exporter, schemas, or tests |
| G3 | Draft PR and CI evidence validate package/export behavior |
| G4 | Separate exact approval required before merge |
| G5/G6 | Not in scope for package export |

## Forbidden interpretations

```text
❌ generated package grants repository write authority
❌ export manifest is gate approval
❌ consumer package replaces protected-base governance
❌ package export permits merge/deploy/release
❌ package export may copy secrets, credentials, production config, or production data
```

## Failure behavior

| Condition | Result |
|---|---|
| Missing required source | Export fails |
| Missing optional source | Export records `skipped_optional` |
| Unsafe source or target path | Export fails |
| Duplicate package id | Export fails |
| Duplicate target path | Export fails |
| Manifest schema violation | Export fails or CI fails |
| Consumer `.governance` package missing | Consumer agent fails closed for repo-changing work |

## Compatibility

This rule is additive. Existing package entries remain valid.

## Non-goals

```text
❌ no package publish service
❌ no automatic consumer repository update
❌ no branch cleanup
❌ no merge authority
❌ no deployment authority
❌ no production data access
```
