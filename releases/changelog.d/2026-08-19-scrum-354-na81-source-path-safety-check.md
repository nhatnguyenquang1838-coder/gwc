feat(gwc): SCRUM-354 NA81-F7 source-path-safety-check recert

Add NA81-specific test coverage for `package_export.source-path-safety-check`
(`tools/node_architect/package_export/source_path_safety.py`, SCRUM-231). The
base evaluator, schema and 19 base tests already existed in the pre-prod line;
this recert pins the NA81-F7-N03 guarantees required by GitHub #289 / Jira
SCRUM-354:

- **Repository-bounded acceptance** -- a regular, in-root source is ACCEPTED
  and bound with a canonical path + sha256 + byte count.
- **Fail-closed on every adversarial class** -- absolute (unix/win), backslash,
  `..` traversal, root escape, symlink escape, directory (non-regular), missing
  required and readback failure all BLOCK; none is ever silently accepted.
- **Required vs optional** -- missing required BLOCKS; missing optional is a
  SKIPPED (skippable) outcome, but an optional entry with an unsafe path still
  BLOCKS.
- **Non-secret / non-authoritative** -- the result never grants repository /
  PR / merge / deploy / release authority (`authority_granted` fixed `False`);
  it binds a read-only source digest only, never a secret scan.
- **Deterministic / replay** -- identical input + filesystem snapshot yields an
  identical `semantic_digest`; verdict ordering is stable and input-order
  independent.
- **No repository / PR / merge / release authority** -- proven by the
  `authority_negative` invariant on every verdict.

New files:
- tests/test_source_path_safety_check_na81.py (NA81 semantics tests, 18 cases)

No `*.node.json` `description`/`source` fields edited (provenance-SHA trap
avoided: the source-path-safety-check.node.json byte SHA still matches the
`source_sha` recorded in node-registry.json; `test_runtime_registry_validation`
stays green).

Parent authority: AR-SCRUM288-RECERT-20260814-R10 (issue #232), task SCRUM-354.
Targets pre-prod only; main is FORBIDDEN.
