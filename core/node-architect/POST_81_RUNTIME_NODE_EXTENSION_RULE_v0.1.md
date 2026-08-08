# Post-81 Runtime Node Extension Rule v0.1

## Status

- Contract ID: `post-81-runtime-node-extension`
- Version: `0.1`
- Lifecycle: active
- Decision task: `SCRUM-284`
- Historical baseline: `REVAMP-GWC-015` / 81 nodes

## Purpose

The original 81-node catalog is an immutable historical baseline. New G1-approved runtime capabilities after that rollout MUST NOT rewrite the baseline count, repurpose an unrelated slot, or silently expand the canonical graph. They are admitted through a separately versioned extension registry.

## Invariants

```text
BASELINE_81_IDENTITIES_ARE_IMMUTABLE
POST_81_NODE_REQUIRES_EXPLICIT_G1_DECISION
EXTENSION_SLOT_STARTS_AT_82_AND_IS_UNIQUE
EXTENSION_NODE_ID_IS_UNIQUE_ACROSS_BASELINE_AND_EXTENSIONS
EXTENSION_PROVENANCE_MUST_MATCH_SOURCE
GRAPH_AND_PROFILE_REFERENCES_MUST_RESOLVE_AGAINST_EFFECTIVE_NODE_SET
UNDECLARED_NODE_GROWTH_FAILS_CLOSED
```

For SCRUM-284 exactly one extension is admitted: `gate_authority.research-review-to-execution` at extension slot 82. The node may validate Human research-execution authority, compile a deterministic execution task, produce reconciliation-first tracking intents, and project bounded task-scoped G2/G3 authority only when the Human parent explicitly delegates those actions.

The node never grants G4, G5, or G6 authority. GitHub/Jira records remain tracking projections and never become gate authority. Trigger source (`immediate_after_approval` or `scheduled_poll`) is observational metadata only.

## Migration and compatibility

`core/node-architect/node-registry.json` continues to contain exactly the original 81 baseline nodes. Runtime validation loads the versioned `runtime-node-extension-registry.json` sidecar and computes the effective node set as baseline plus admitted extensions; an optional registry reference is reserved for future producers but is not required for the historical baseline file. The runtime graph/profile may reference extension nodes only when the extension registry validates first.

The historical 81-node expansion plan and its validator remain unchanged.
