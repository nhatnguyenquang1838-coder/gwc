# Observable decisions

## Decision 1 — repository ownership
Evidence: current DW-SuperApps and GWC contracts.
Alternatives: one umbrella repo; duplicate policy in both repos; independent repo lanes.
Decision: independent repository lanes `SCRUM-554` with separate base/branch/authority.
Confidence: high.

## Decision 2 — canonical specification
Evidence: user selection B and current Task-Me skill boundary.
Decision: Task-Me package is canonical; no competing `docs/superpowers/**` spec tree.
Confidence: high.

## Decision 3 — architecture boundary
Put capability vocabulary and authority-closure semantics in GWC; TaskController consumes the result. Gate names remain compatible projections, not the sole semantic source.
Confidence: high.

## Unresolved uncertainty
No design uncertainty blocks the spec. Exact implementation file set may narrow after fresh-session drift/materialization readback; narrowing is allowed, scope expansion is not.
