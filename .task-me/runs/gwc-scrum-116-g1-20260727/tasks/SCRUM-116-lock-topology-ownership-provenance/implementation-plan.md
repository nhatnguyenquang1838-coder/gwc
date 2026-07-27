# Implementation plan

1. Read the accepted G1 plan and exact protected-base paths; write a G2 plan-read receipt before any repository mutation.
2. Author the topology, source-of-truth, ownership and projection matrix using verified DW-SuperApps and GWC contracts.
3. Add a versioned provenance envelope with artifact/parent IDs, source repo/ref/SHA, tool package/source commit, schema version, owner root and generated time.
4. Model positive provenance, stale lease/fencing/CAS rejection, idempotency collision and scope mismatch examples.
5. Define compatibility behavior for submodule, power-dist, immutable release and offline ZIP inputs, including explicit absent boilerplate and `ready-unpublished` states.
6. Add focused validators/tests and review the complete diff against the approved file list.

The plan is intentionally output-only in G1. Product source and canonical runtime behavior remain unchanged until a valid G2 approval is supplied.
