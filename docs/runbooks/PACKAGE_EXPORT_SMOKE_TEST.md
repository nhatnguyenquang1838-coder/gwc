# Package Export Smoke Test

## Status

```text
Runbook ID: PACKAGE_EXPORT_SMOKE_TEST
Introduced by: REVAMP-GWC-008
Applies to: projects/gwc/package.yaml generated .governance export
```

## Purpose

Verify after merge that the GWC consumer package can be exported into a generated `.governance/` tree and that the export manifest matches copied bytes.

## Scope

This runbook verifies package export behavior only. It does not create consumer repository commits, publish packages, merge PRs, deploy, release, change production configuration, read credentials, run migrations, or access production data.

## Required command

```bash
python tools/verify_package_export_smoke.py \
  --root . \
  --package projects/gwc/package.yaml \
  --source-ref main \
  --source-base-sha <40-character-main-sha>
```

Optional retained output:

```bash
python tools/verify_package_export_smoke.py \
  --root . \
  --package projects/gwc/package.yaml \
  --source-ref main \
  --source-base-sha <40-character-main-sha> \
  --output /tmp/gwc-package-export-smoke
```

## Expected checks

```text
✅ exporter runs against the real GWC package manifest
✅ generated .package-export-manifest.json exists
✅ project_id is gwc
✅ package_version remains 1.16.0
✅ source_base_sha is the provided exact SHA
✅ required entries are copied
✅ optional missing entries are recorded as skipped_optional
✅ copied target files exist under generated .governance/
✅ manifest sha256 equals source bytes and generated target bytes
✅ required REVAMP export artifacts exist in the generated output
```

## Required generated artifacts

The smoke test must verify at least these generated targets:

```text
.governance/core/node-architect/CONSUMER_PACKAGE_EXPORT_RULE_v0.1.md
.governance/schemas/package-export-manifest.schema.json
.governance/tools/export_project_package.py
.governance/tools/verify_package_export_smoke.py
.governance/docs/runbooks/PACKAGE_EXPORT_SMOKE_TEST.md
```

## Failure behavior

| Condition | Result |
|---|---|
| Exporter exits with error | smoke test fails |
| Required package entry is missing | smoke test fails |
| Required target missing from `.governance/` | smoke test fails |
| Manifest count differs from copied/skipped entries | smoke test fails |
| SHA-256 mismatch | smoke test fails |
| Package version unexpectedly changes | smoke test fails |

## Authority boundary

The generated `.governance/` tree and `.package-export-manifest.json` are evidence only. They do not grant write, PR, merge, deploy, release, production configuration, credential, migration, or production-data authority.
