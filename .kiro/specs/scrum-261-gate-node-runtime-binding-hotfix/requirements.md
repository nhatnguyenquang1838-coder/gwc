# SCRUM-261 Expanded Hotfix Requirements

## Objective
Restore the protected-base validation broken by merged PR #173, then implement the bounded GWC gate-to-Node-Architect runtime binding slice on the same guarded hotfix branch.

## Active lane and bounded recovery exception
- Active lane remains `SCRUM-256 — Client runtime binding and CI → G3 M5 vertical slice`.
- The PR #173 intake-card repair is admitted only as a prerequisite recovery exception because the current protected base fails repository validation and blocks this lane.
- This does not select the broader intake-context maturity lane or authorize unrelated SCRUM-182 work.

## In scope
1. Repair `tools/node_architect/intake_card_render.py` so upstream BLOCKED state survives redaction, stable reason-code tokens are emitted, and protected key matching covers suffix forms such as `api_token`.
2. Repair invalid assertions in `tests/test_intake_context_intake_card_render_m4.py` without weakening intended behavior.
3. Add the gate-node runtime binding contract, route profile, schemas, resolver, tests, and ChatGPT instruction binding.
4. Preserve G0-G6 authority boundaries and fail closed on missing/ambiguous/non-executable routes.
5. Run LF/UTF-8 validation first, focused tests, full governance tests, registry validation, instruction validation, compile checks, and exact-head CI.

## Acceptance criteria
- AC-1: The PR #173 intake-card suite passes all tests, including upstream BLOCKED propagation, stable reason codes, digest length checks, explicit redaction, and `api_token` redaction.
- AC-2: Full governance unit tests pass on the combined branch.
- AC-3: A G2 repository-write request resolves deterministically through `repo_delivery.scoped-file-write`.
- AC-4: Missing G0/G1/G2 context returns `NODE_CONTEXT_NOT_LOADED` and grants no authority.
- AC-5: Missing, ambiguous, catalog-only, maturity-ineligible, or implementation-unavailable routes fail closed with stable reason codes.
- AC-6: Route profile and decision output validate under JSON Schema Draft 2020-12.
- AC-7: Successful scoped write routes to `repo_delivery.diff-readback`, then to the next exact node or human gate.
- AC-8: ChatGPT instructions require context rehydration and resolver invocation before G2 writes.
- AC-9: New and modified text is UTF-8 without BOM and LF-normalized before hashes or later validation.
- AC-10: No G4/G5/G6, merge, deployment, release, production data/configuration, secret, migration, force-push, branch deletion, or PR-base-change authority is introduced.

## Done-state integrity
Merged PR #173 is not accepted as valid dependency evidence because its exact PR-head `Validate instructions` workflow failed with 8 failures and 2 errors. It is treated as a merged-but-invalid prerequisite requiring bounded repair.
