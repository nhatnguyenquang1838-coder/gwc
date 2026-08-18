# Implementation plan

**Fresh implementation session required.** Use TDD and exact-base drift readback before modifying source. GWC is the normative owner of the capability vocabulary and causal-effect authority semantics consumed by TaskController.

## Step 1 — Capability registry
Define a versioned machine-readable capability registry that separates semantic capabilities from gate labels while preserving existing G0-G6 projections. At minimum distinguish read-only/compute, guarded repo write, PR mutation, merge, release/publish, **destructive/delete/retention**, production data/config, secret/credential and migration.

Validation checkpoint: registry schema + compatibility tests; no silent gate renumbering.

## Step 2 — Effect graph and conditional semantics
Define a transitive-effect graph schema with exact source action identity, predicate evidence, edge state (`deterministic` or `conditional`), affected repository/environment, capability, required authority, evidence/readback identity and graph digest.

Normative conditional policy:
- predicate proven `false` -> edge is excluded only with predicate evidence bound to the parent action identity;
- predicate `true` -> child is reachable;
- predicate `unknown` -> a mutating/cross-repo/release/destructive/production-capable child is potentially reachable and must be authority-closed at its worst-case capability or the parent action is blocked;
- unresolved read-only/compute children may remain non-escalating but must remain observable.

Validation checkpoint: true/false/unknown fixtures, including cross-repo and destructive children.

## Step 3 — Packet binding and legacy compatibility
Extend the gate-action authority packet/schema with effect-graph ref/digest and requested capability identity. Compatibility is explicit and closure-preserving:
- legacy packets lacking a per-packet effect graph may use a versioned trusted effect profile bound to the exact action identity;
- `NO_TRANSITIVE_MUTATION` is the trivial profile proving no mutating transitive effect exists;
- `BOUNDED_TRANSITIVE_EFFECTS` contains a complete precomputed closure for deterministic and potentially reachable conditional effects, including affected repository/environment, capability, predicate policy and profile digest;
- the trusted profile may substitute for a per-packet graph only when current/complete and every child effect is already inside the packet authority or has independent repository/capability authority;
- trigger-capable or unknown-profile actions with neither a valid graph nor a complete trusted profile fail closed with `EFFECT_GRAPH_REQUIRED`;
- profile digest/version is bound to the authority decision; profile drift invalidates the decision.

Validation checkpoint: safe no-trigger legacy packet passes; legacy trigger-capable packet with complete read-only/fully-authorized profile passes; same action with incomplete/unknown profile or unauthorized child fails closed.

## Step 4 — Causal authority closure
Compute closure across deterministic and potentially reachable conditional children. Reject a parent action when any child capability/repository is unauthorized. Safe read-only children must not spuriously escalate authority. Cross-repo mutations require independent authority for the affected repo.

Validation checkpoint: direct-authorized/child-unauthorized, cross-repo, safe-read-only and unknown-condition cases.

## Step 5 — Exact evidence consumption identity
Bind evidence to repository + event/action + branch/PR + exact SHA + run/check + gate/node identity. Reject wrong-node reuse and historical-success substitution. A successful run for another SHA/event/gate is evidence of that historical execution only, never authority for the current packet.

Validation checkpoint: PR-head-vs-merge-SHA and prior-success-different-SHA/gate fixtures.

## Step 6 — Incident and destructive regressions
Add regression fixtures for `G4 merge -> push main -> export archive -> release-dist write + retention delete`, multi-repo child effects, conditional predicates, drift/replay and historical success. Explicitly assert that retention deletion maps to destructive capability rather than being absorbed into ordinary release/publish.

Validation checkpoint: incident fixture must fail before required child authority and pass only when every reachable/potentially reachable effect is covered.

## Step 7 — Normative lifecycle/docs
Update lifecycle documentation/map only where required to make capability/effect semantics normative without renumbering existing gates. Document compatibility profile, reason codes and policy digest requirements so gate labels remain projections rather than a second semantic source.

Validation checkpoint: schema/docs/validator tests agree on one capability/effect source of truth.

## Delivery boundary
Implementation commits belong to a fresh G2-authorized implementation branch/session, not this spec-only branch. G3/G4/G5/G6 remain separate authority boundaries.
