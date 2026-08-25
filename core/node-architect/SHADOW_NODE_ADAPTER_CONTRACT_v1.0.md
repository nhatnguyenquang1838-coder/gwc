# Shadow Node Adapter Contract v1.0

Every canonical baseline node is bound to a read-only shadow adapter. The adapter may evaluate declared node semantics and return a recommendation, but it cannot call a write-capable provider.

## Interface

`execute_shadow_node(node, event, input_payload) -> ShadowNodeResult`

Required event identity: `task_id`, `run_id`, `gate`, `exact_revision`.

## Safety

- `mode = shadow_readonly`
- `authority = none`
- `output_effect = observe_only`
- write-class nodes return `WOULD_REQUEST_ACTION` plus proposed effects only
- `executed_effects` is always empty
- suspendable nodes may recommend checkpoint/resume metadata but never persist canonical state
- missing event identity fails closed as `BLOCKED`
- deterministic digest excludes no hidden runtime state

The adapter layer binds baseline 81 only; extension slot 82 never substitutes for missing baseline coverage.
