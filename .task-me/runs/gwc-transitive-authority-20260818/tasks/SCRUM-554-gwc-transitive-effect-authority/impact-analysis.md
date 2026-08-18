# Impact analysis

## Direct surfaces
- `schemas/gate-action-authority.schema.json`
- new focused effect/capability schema(s) as required
- `tools/validate_gate_action.py` and/or a focused pure helper
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md`
- `core/task-lifecycle/gate-transition-map.yaml` only where semantics require it
- focused tests

## Causal impact
- A direct governed action can trigger deterministic or conditional workflows/hooks/bots with release, delete/retention, cross-repo, deployment or production consequences.
- Conditional mutating effects remain in worst-case authority closure until predicate=false is proven.
- Retention deletion is a destructive capability distinct from release/publish.
- Cross-repo child effects require independent authority for the affected repo.
- SCRUM-553 consumes this capability/effect contract; GWC policy drift therefore invalidates downstream TaskController preflight receipts.

## Compatibility risk
- Blanket acceptance of legacy packets without an effect graph would preserve the observed authority leak.
- Blanket rejection would unnecessarily break safe no-trigger actions. The versioned `NO_TRANSITIVE_MUTATION` compatibility profile is the bounded bridge.

## Primary failure modes
- false PASS on unknown conditional mutations;
- historical green run reused as authority;
- deletion folded into a lower release capability;
- dual semantic sources between gate names and capability registry;
- effect graph/policy drift without re-authorization.
