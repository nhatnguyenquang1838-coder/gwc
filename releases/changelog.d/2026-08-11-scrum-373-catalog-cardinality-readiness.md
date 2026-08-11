# SCRUM-373 — Catalog cardinality readiness NA81 maturity

## Type

```text
feature
```

## Summary

Promotes `scale_control.catalog-cardinality-readiness` from a historical M4
validator to an instruction-backed executable NA81 node. Readiness now derives
from the canonical repository/catalog evidence and deterministically rejects
wrong family membership (a node under the wrong family), duplicate / missing /
extra IDs, and version/cardinality drift. Jira count alone is never readiness
proof.

## Guardrails

```text
CATALOG_READINESS_COMES_FROM_CANONICAL_INVENTORY_NOT_JIRA_COUNT.
SCALE_CONTROL_EVIDENCE_DOES_NOT_GRANT_SCALE_AUTHORITY.
Readiness computation never grants scale, audit, or deployment authority.
```
