# Implementation plan

> **Fresh-session only.** Re-read current main and this exact spec PR head before any source edit. If drift changes authority/workflow semantics, return to G0/G1 instead of silently adapting.

## Step 1 — Capability registry and schemas
Define machine-readable capability semantics independent from gate-number labels. Include at minimum `read_only`, `compute`, `merge`, `release`, `deploy`, `migration`, `destructive`, and `production_data` capability classes, plus independent affected-repository/environment identity. Define the trusted effect profile schema alongside effect graph identity.

Validation checkpoint: capability registry and schema fixtures parse; deletion/retention is explicitly destructive.

## Step 2 — Effect graph and conditional policy
Represent direct parent and transitive children with trigger/event, deterministic vs conditional classification, predicate state/evidence when conditional, affected repo/environment, capability and mutation type.

Normative conditional policy:
- `predicate=false` + bound evidence => child excluded from authority closure;
- `predicate=true` => child reachable and included;
- `predicate=unknown` + mutating/cross-repo/release/deploy/migration/destructive/production capability => potentially reachable and included at worst-case capability;
- unknown read-only/compute child remains observable and does not spuriously escalate beyond its own capability.

Validation checkpoint: true/false/unknown fixtures yield deterministic closure.

## Step 3 — Backward-compatible packet extension
Preserve existing compatible direct-action packets, but never infer `absent effect graph == no effects`.

Introduce a versioned trusted action effect profile bound to exact action identity:
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
