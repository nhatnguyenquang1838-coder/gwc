# Implementation plan

1. Discover and verify the canonical manifest destination using existing
   package/export and evidence conventions; stop if no governed destination is
   found.
2. Collect exact P1–P5 refs and classify each claim with provenance and
   maturity; include known P5 final refs and stale-G3 mismatch as separate
   evidence, never as a false pass.
3. Resolve exact-SHA CI status with `resolve_g5_status.py` and validate with
   `validate_g5_status.py`; reconcile GitHub/Jira projection using the existing
   validator without granting authority.
4. Bind prerequisite 147–149 evidence and residual risks to the exact current
   head/base and generate human-readable and machine-readable closure records.
5. Validate the complete diff and all manifest hashes; stop at G3 Draft PR and
   prepare a separate G4 request.
