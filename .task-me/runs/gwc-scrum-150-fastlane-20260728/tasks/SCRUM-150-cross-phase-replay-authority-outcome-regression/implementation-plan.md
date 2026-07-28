# Implementation plan

1. Define the smallest JSON record shape needed to join P2/P3/P4/P5 and exact
   G4/G5 evidence without duplicating their authorities.
2. Implement pure validation functions with stable issue codes. Reject missing
   dependency evidence, stale base/head/merge/CI bindings, duplicate effects,
   replay divergence without typed state divergence, fabricated metrics,
   projection authority leakage, and automatic promotion.
3. Reuse existing validator semantics where possible; do not modify existing
   validators unless a verified compatibility seam is required.
4. Add one contract-positive fixture and typed negative fixtures for each
   rejection class.
5. Add focused unit tests for acceptance, stale dependency evidence, replay,
   metric provenance, human controls, projection outage, and authority leakage.
6. Run focused tests, `git diff --check`, and the applicable existing validator
   suites. Report unrun live-provider/host/deployment checks explicitly.
