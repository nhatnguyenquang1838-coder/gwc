feat(gwc): SCRUM-338 NA81-F5 evidence-quality-check NA81 semantics

Re-verify the existing `validation_quality.evidence-quality-check` node under the
NA81 recert (SCRUM-338 / GitHub #273, Family SCRUM-293, Epic SCRUM-288) with
current task-bound evidence.

The node implementation already exists (SCRUM-215/219/256, PR #180, commit
4a43439) and is classified VERIFIED_REUSE: historical SCRUM-215 is reuse
evidence only and no descriptor or code delta is required for this task.

What this change delivers (DELTA_REQUIRED = tests + evidence only):

- `tests/test_validation_quality_evidence_quality_check_na81_f5.py` adds focused
  NA81-F5 scenarios proving the node's fail-closed evidence-quality contract:
  * complete / exact-head evidence -> PASS (EVIDENCE_ACCEPTED);
  * stale evidence (evaluated long after reviewed) -> BLOCKED (EVIDENCE_STALE);
  * incomplete evidence (missing ci_evidence / review_receipt) -> BLOCKED
    (EVIDENCE_INCOMPLETE);
  * mixed-head (review head != identity head) -> BLOCKED (EVIDENCE_HEAD_MISMATCH);
  * conflicting terminal CI conclusions -> BLOCKED (EVIDENCE_CONTRADICTORY);
  * projection-only source (jira/slack/notion) -> BLOCKED (EVIDENCE_PROJECTION_ONLY);
  * deterministic replay via replay_cache -> stable quality_digest, replayed=True.

The node descriptor (`core/node-architect/node-catalog/validation_quality/
evidence-quality-check.node.json`) is data-only and intentionally untouched;
provenance SHA preserved (no provenance-Sha trap regression).

Required gates: focused/neighbor/F5 validator + exact-head CI/G3 green; the node
grants no merge/deploy/production authority (authority_boundary all False).

This change is mechanical only -- no autonomous merge / main action. The PR
targets pre-prod only; main is FORBIDDEN.

Parent authority: R10 (issue #232), run SCRUM-288-NA81-RECERT-20260814-R10,
task SCRUM-338. This fragment grants no merge, deploy, release, production
configuration, credential, migration, or production-data authority.
