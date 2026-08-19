feat(gwc): SCRUM-351 NA81-F6 projection-privacy-boundary-check NA81 semantics

Implement the missing SCRUM-351 (NA81-F6-N09) NA81 semantics on top of the
existing sync_projection projection-privacy-boundary-check evaluator
(`tools/node_architect/projection_privacy_boundary_check.py`, SCRUM-228).
The base `decide_projection_privacy` performs the closed, fail-closed privacy
classification but did not assert the explicit SCRUM-351 requirements
(DELTA_REQUIRED):

- **Deterministic field disposition** -- every field resolves to ALLOW /
  SANITIZE / DENY via `na81_disposition_for(...)`; sanitizable restricted
  classes are redacted/removed per policy, prohibited classes are denied, and
  no raw secret/credential/production data is ever projected.
- **Unknown classification fails closed** -- an explicit but unrecognized
  classification (or an unclassified mandatory protected key) is never
  projected and BLOCKS the boundary decision.
- **Deterministic / replay idempotency** -- identical inputs yield an identical
  `privacy_boundary_digest` (na81.deterministic); classification order does not
  affect the digest.
- **Policy drift** -- a changed redaction `policy_revision` changes the digest.
- **Explicit non-authoritative guarantee** -- `read_only_projection` fixed
  true, every authority field fixed false; the boundary decision is never
  canonical task truth (PROJECTION_IS_NOT_CANONICAL_TASK_TRUTH).
- **No secrets/credentials in output** -- residual leak scan on the sanitized
  payload; the projection never carries raw protected values (even when blocked).

Backward-compatible: `decide_projection_privacy` is unchanged and reused as the
decision engine; the base decision is preserved verbatim under
`privacy_decision`.

New behavior (DELTA_REQUIRED, backward-compatible -- `decide_projection_privacy`
is unchanged and reused as the privacy engine):

- `decide_projection_privacy_na81(...)` reuses `decide_projection_privacy` and
  adds the SCRUM-351 NA81 assertions plus a consumer-bindable
  `privacy_boundary_digest`.
- `na81_disposition_for(...)` exposes the deterministic ALLOW/SANITIZE/DENY
  mapping the brief requires.

New files:
- tests/test_projection_privacy_boundary_na81.py (NA81 semantics tests)

Updated files:
- tools/node_architect/projection_privacy_boundary_check.py
  (decide_projection_privacy_na81, na81_disposition_for)

No `*.node.json` `description`/`source` fields edited (provenance trap avoided).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-351.
Targets pre-prod only; main is FORBIDDEN.
