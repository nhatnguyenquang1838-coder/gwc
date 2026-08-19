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
Legacy packets without per-packet effect graphs do not receive blanket grandfathering. They may remain compatible under a versioned trusted effect profile bound to the action identity and authority decision:
- `NO_TRANSITIVE_MUTATION` proves no mutating transitive effect exists;
- `BOUNDED_TRANSITIVE_EFFECTS` enumerates the complete deterministic and potentially reachable conditional closure, affected repo/environment, capability and predicate policy.
A trigger-capable legacy action is compatible only when the trusted profile is current, complete, digest-bound, and every reachable/potentially reachable child is already within the current authority or has independent authority. Missing/incomplete/unknown profile evidence requires an effect graph and fails closed.
Confidence: high.

## Decision 6 — destructive retention
Deletion/retention effects are classified as destructive capability, distinct from ordinary release/publish writes.
Confidence: high.

## Remaining implementation uncertainty
Exact implementation file set may narrow after fresh-session readback. Schema field names/reason-code spelling may refine within these semantics, but the authority behavior above is fixed by this spec.
