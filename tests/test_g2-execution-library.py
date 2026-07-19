# Test suite for G2 Execution Library Integrity

## Objective
Validate that the `gwc-g2-execution-library` correctly binds, executes, and enforces transaction boundaries during the G2 phase.

## Test Cases to Implement
1. **Binding Test:** Verify that any action taken when G0/G1 proofs are missing or invalid results in a `G2_ACTION_BLOCKED` failure, matching the manifest contract.
2. **Atomic Execution Test:** Simulate a complex change and verify that it is executed as a single, atomic transaction bound to the G1 approval hash.
3. **Constraint Test:** Simulate an attempt by `skills/g2-execution-plan.md` to perform a prohibited action (e.g., merging) and verify that `skills/g2-repository-interaction.md` successfully blocks the action and logs a failure trace.
4. **Rollback Scenario:** Simulate the execution flow being interrupted midway and verify that no partial or dangerous state change has occurred in the base repository.

## Dependencies
- `gwc-g2-execution-library/manifest.yaml`
- `gwc-g2-execution-library/skills/g2-execution-plan.md`
- `gwc-g2-execution-library/skills/g2-repository-interaction.md`

# Test execution command (Conceptual)
python tests/test_g2-execution-library.py --suite gwc-g2
