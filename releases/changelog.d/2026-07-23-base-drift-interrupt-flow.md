# Base drift interrupt flow

- Add `core/INTERRUPT_FLOW_CONTRACT_v1.0.md` to define shared interrupt, checkpoint, resume, reroute, and stop semantics.
- Extend base-drift policy and evaluator output with reason codes, authority effects, evidence effects, and continuation modes.
- Add interrupt frame and node-interruptibility schemas.
- Extend the runtime_checkpoint node family with five base-drift interrupt nodes.
- Add validator and tests for interrupt-flow and base-drift behavior.
