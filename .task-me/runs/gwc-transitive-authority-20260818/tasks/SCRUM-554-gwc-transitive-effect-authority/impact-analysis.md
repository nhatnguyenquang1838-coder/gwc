# Impact analysis

## Candidate implementation surfaces (re-verify in fresh session)
- `schemas/gate-action-authority.schema.json`
- focused new capability/effect graph and trusted-effect-profile schema(s)
- `tools/validate_gate_action.py` and, if justified, a pure closure helper
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `core/task-lifecycle/gate-transition-map.yaml` only where capability semantics require projection changes
- focused validator tests under current `tests/` layout

## Transitive impact
- direct G4-like action may deterministically trigger release/write/delete behavior;
- conditional trigger predicates must resolve as true/false/unknown with fail-closed treatment for unknown mutating effects;
- cross-repo child effects require independent authority;
- evidence/policy/effect digests must stay bound to the execution identity;
- legacy compatibility must be explicit and bounded, not inferred from absence of graph fields;
- trusted effect profiles themselves become governed semantic evidence and must be version/digest bound.

## Risk
- old direct packets may not carry new effect graph fields;
- blindly making graph fields mandatory would break compatibility;
- blindly treating absent graph as no effects would preserve the authority leak;
- a single `NO_TRANSITIVE_MUTATION` profile is insufficient because some legacy trigger-capable actions may have read-only or otherwise already-authorized children and still satisfy issue AC8;
- capability semantics can drift from gate labels if dual sources are created;
- effect graph/profile drift after approval can stale authority;
- conditional edge omission can recreate the Rental Home failure class;
- destructive retention can be hidden under a broad release capability.

## Mitigation direction
- versioned effect/capability semantics with explicit compatibility handling;
- trusted action effect profile (`NO_TRANSITIVE_MUTATION` or complete `BOUNDED_TRANSITIVE_EFFECTS`) may satisfy legacy packets only when profile identity/version/digest and complete closure are bound to the decision;
- trigger-capable/unknown action without valid graph or complete trusted profile fails closed;
- one normative capability registry consumed by validator/docs;
- deterministic reason codes for missing/unauthorized/drifted effect evidence;
- regression fixture for merge→release-dist→retention delete.
