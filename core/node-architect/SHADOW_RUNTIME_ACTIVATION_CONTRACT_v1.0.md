# Shadow Runtime Activation Contract v1.0

The canonical shadow runtime is enabled only when `core/node-architect/shadow-runtime-activation.json` is valid and all safety predicates pass.

## Required invariants

```text
enabled = true
kill_switch_engaged = false
mode = shadow_readonly
authority = none
output_effect = observe_only
exact_revision_binding = true
decision_authority = false
automatic_gate_advance = false
```

Missing/invalid activation, engaged kill switch, or revision drift returns `SHADOW_DISABLED_FAIL_CLOSED` and executes zero nodes.

The observer consumes the same immutable gate event identity used by the authoritative path, but its output has `authoritative_effect = NONE`. It may select scenario routes and invoke read-only shadow adapters only.

The pull-request observer is the first live hook: every eligible PR event is represented as `G3_PR / standard_pr_delivery`, evaluated on the exact PR head SHA, and uploaded as non-authoritative evidence.
