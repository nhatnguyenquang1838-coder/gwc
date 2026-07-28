# Implementation plan

1. Verify the exact base, package/source versions, and host-mode contract
   inputs from the two prerequisite lanes.
2. Execute one bounded UA/Task-Me/BMAD/GitHub/CI path through approved adapters.
3. Build/install the supplied package in a clean offline consumer workspace and
   run doctor, instruction discovery, and no-production governed pilot checks.
4. Exercise stale artifacts, provider unavailability, duplicate side effects,
   projection authority leakage, and replay divergence.
5. Validate all evidence with `validate_dw_super_e2e_pilot.py` and the existing
   host/package validators; record live-call versus fixture evidence separately.
