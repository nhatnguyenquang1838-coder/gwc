
---
extension_id: replace-project-conventions
version: "1.0"
authoritative: false
extends_profile: replace-project-id
core_policy: CODING-PROJECT-GOVERNANCE@1.0
core_sha256: 04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1
mode: tighten_only
---

# Project Extension

## Architecture

Add project-specific boundaries that tighten the core policy.

## Security and data

Add auth, authorization, privacy, migration, production-data, and secret rules.

## Repository

Add connector, protected branch, worktree, and PR conventions.

## Validation

List mandatory tests and evidence.

## Activation

Keep repository writes disabled until identity and protected-base governance
are verified.
