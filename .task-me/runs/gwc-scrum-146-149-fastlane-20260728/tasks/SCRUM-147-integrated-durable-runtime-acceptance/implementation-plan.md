# Implementation plan

1. Re-read the durable runtime contracts and the current store/harness APIs.
2. Map each SCRUM-147 scenario to checkpoint revisions, lease/fencing state,
   pending side-effect state, and deterministic replay evidence.
3. Extend the smallest existing runtime seam for missing integrated behavior.
4. Add positive and negative tests for success, rejection, crash before/after
   side effect, stale checkpoint/lease/CAS, ambiguous provider state, and
   duplicate replay.
5. Validate focused tests, schema/package invariants, and exact changed-file
   scope before handing evidence to SCRUM-149.
