feat(gwc): SCRUM-350 NA81-F6 projection-evidence-linking fail-closed maturity gap

Implement the missing SCRUM-350 (NA81-F6-N08) evidence-linking defenses on top
of the existing sync_projection `projection-evidence-linking` evaluator
(`tools/node_architect/projection_evidence_linking.py`, SCRUM-227). The base
evaluator already enforced broken/stale/unverified/conflict/untrusted link
rejection; the brief required two further fail-closed checks (DELTA_REQUIRED):

- **Circular link defense** -- a cycle over the SUPERSEDES revision graph
  (a revision that simultaneously supersedes and is superseded by another) is
  detected by `_has_supersede_cycle` and fails closed. Acyclic history chains
  remain valid.
- **Projection-derived source defense** -- an evidence link that reuses a
  source binding whose `authority_class` is `PROJECTION` (even when VERIFIED)
  is rejected. A projection artifact is never canonical provenance
  (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH).

Both reuses the schema-valid `EVIDENCE_LINK_CONTRACT_INVALID` reason so the
linkset artifact stays within the `projection-evidence-linkset` schema
`reason_code` enum (that schema file lives outside the authorized change paths
and is intentionally unchanged).

Backward-compatible: `_authority_is_valid` return contract and all existing
call-sites are unchanged; only an inline projection-source collection was added
to `build_projection_evidence_linkset`.

New files:
- tests/test_projection_evidence_linking_scrum350.py (8 NA81 maturity tests:
  valid link, broken source, stale source digest, circular link, acyclic
  chain, projection-derived source, duplicate replay determinism, no-authority
  implication)

Updated files:
- tools/node_architect/projection_evidence_linking.py (EVIDENCE_LINK_CIRCULAR
  cycle detection + projection-derived source rejection)

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-350.
Targets pre-prod only; main is FORBIDDEN. No *.node.json description/source
fields edited (provenance trap avoided).
