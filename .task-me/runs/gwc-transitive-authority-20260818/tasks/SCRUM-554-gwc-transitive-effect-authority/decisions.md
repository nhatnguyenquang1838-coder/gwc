# Observable decisions

## Decision 1 — repository ownership
Decision: SCRUM-554 is an independent GWC lane with its own base/branch/authority. SCRUM-553 is a downstream consumer, not shared authority.
Confidence: high.

## Decision 2 — canonical specification
Decision: Task-Me package is canonical; no competing `docs/superpowers/**` spec tree.
Confidence: high.

## Decision 3 — architecture boundary
GWC owns capability vocabulary and causal authority-closure semantics. TaskController consumes an exact policy identity; gate names remain compatible projections, not the sole semantic source.
Confidence: high.

## Decision 4 — conditional effects
A conditional mutating child is excluded only when predicate=false is proven. Predicate=true is reachable. Predicate=unknown is potentially reachable and must be authority-closed at worst-case capability or blocked. Read-only unknown children remain observable without unnecessary escalation.
Confidence: high.

## Decision 5 — legacy compatibility
Legacy packets without effect graphs do not receive blanket grandfathering. They remain compatible only under a versioned trusted `NO_TRANSITIVE_MUTATION` action profile; trigger-capable or unknown actions require an effect graph and fail closed when absent.
Confidence: high.

## Decision 6 — destructive retention
Deletion/retention effects are classified as destructive capability, distinct from ordinary release/publish writes.
Confidence: high.

## Remaining implementation uncertainty
Exact implementation file set may narrow after fresh-session readback. Schema field names/reason-code spelling may refine within these semantics, but the authority behavior above is fixed by this spec.
