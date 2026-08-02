# SCRUM-261 Expanded Hotfix Design

## Delivery sequence
1. Branch from exact protected base `0b05dcce1865cdce58e5fff22ee8784428735df0`.
2. Repair the intake-card baseline first.
3. Run the intake-card suite and full governance suite; do not proceed to route binding while baseline repair is red.
4. Implement the provider-neutral gate-node resolver slice.
5. Run all focused and repository validators, perform exact diff readback, commit, push, and check CI for the exact head SHA.

## Intake-card repair
- Keep `reason_codes` machine-stable: emit base codes such as `CARD_INPUT_INVALID`; preserve detail separately only when needed.
- Preserve `BLOCKED` outcome through redaction. Redaction may change `redaction_status` and append `CARD_RENDERED_REDACTED`, but must never upgrade BLOCKED to READY.
- Expand protected-key recognition to underscore-suffixed forms such as `api_token`, while avoiding broad substring matching.
- Replace non-standard `assertLen` test calls with standard length assertions.

## Gate-node binding
- A closed route profile maps `(gate, requested_action)` to a current node, required context, implementation entry point, next node, and next gate boundary.
- The resolver is pure and side-effect-free. It validates graph/profile revisions and node registry maturity/implementation state.
- G2 repository writes route through `repo_delivery.scoped-file-write`; PASS routes to `repo_delivery.diff-readback`.
- No route grants authority. Authority remains exclusively in validated gate artifacts.

## Fail-closed codes
`NODE_CONTEXT_NOT_LOADED`, `NODE_ROUTE_MISSING`, `NODE_ROUTE_AMBIGUOUS`, `NODE_CONTRACT_MISSING`, `NODE_CONTRACT_INCOMPLETE`, `NODE_IMPLEMENTATION_UNAVAILABLE`, `NODE_NOT_EXECUTABLE_AT_MATURITY`, `GATE_NODE_BINDING_MISMATCH`, `GRAPH_REVISION_DRIFT`, `PROFILE_REVISION_DRIFT`.

## Rollback
Stop before push on any validation or scope failure. Leave the guarded branch intact for audit. Do not delete or rewrite history.
