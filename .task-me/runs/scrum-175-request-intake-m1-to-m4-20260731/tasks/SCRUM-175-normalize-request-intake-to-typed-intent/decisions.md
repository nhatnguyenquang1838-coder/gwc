# Decisions

## Decision 1

- **Evidence used:** `request-intake.node.json`, family README, validator, tests, runtime graph, node registry.
- **Alternatives considered:** Create a new family or a separate runtime helper.
- **Rule applied:** Reuse the existing bounded family when the node identity already exists.
- **Decision:** Keep the change inside `intake_context.request-intake`.
- **Confidence:** High.
- **Unresolved uncertainty:** The exact shape of the new typed intake fields is not yet implemented and must be validated against the final source contract.

## Decision 2

- **Evidence used:** current validator and regression tests.
- **Alternatives considered:** Loosen the validator entirely or only update the node descriptor.
- **Rule applied:** Fail closed on malformed or ambiguous input.
- **Decision:** Update the validator and tests together with the node contract.
- **Confidence:** High.
- **Unresolved uncertainty:** Whether a helper or schema artifact is needed can only be decided after implementation-level inspection.

## Decision 3

- **Evidence used:** Kiro delivery rule and G0/G1 operational runbook.
- **Alternatives considered:** Treat the node change as a free-form doc edit.
- **Rule applied:** Preserve G0-only read-only authority and exact-head evidence discipline.
- **Decision:** Keep the plan as a bounded planning artifact with validation commands and exact-head evidence capture.
- **Confidence:** High.
- **Unresolved uncertainty:** None for planning scope; the repository still needs implementation evidence before any stronger claim is made.
