feat(gwc): SCRUM-342 NA81-F5 g3-pass-decision NA81 semantics

Implement the missing SCRUM-342 (NA81-F5-N09) NA81 semantics on top of the
existing `decide_g3_pass` G3 renderer (SCRUM-219). The core renderer already
performs the fail-closed G3 decision with a deterministic digest, replay cache
and authority boundary (merge/deploy/production=False); it lacked the explicit
SCRUM-342 NA81-F5-N09 assertions on its own surface.

New behavior (DELTA_REQUIRED, backward-compatible -- `decide_g3_pass` is
unchanged and reused as the decision core):

- `decide_g3_pass_na81(...)` reuses `decide_g3_pass` and adds:
  * deterministic / replay idempotency -- identical inputs yield an identical
    na81_decision_digest (na81.deterministic / na81.idempotent);
  * explicit authority boundary -- no merge / approval / deployment /
    production authority is granted (approval_authority_granted surfaced False
    and the core authority boundary embedded);
  * fail-closed -- if the core returns a non-PASS outcome caused by
    EVIDENCE_REJECTED / HEAD_DRIFT / REQUIRED_EVIDENCE_MISSING the NA81 result
    stays BLOCKED (never silently passes; NA81_FAIL_CLOSED asserted);
  * explicit non-authoritative guarantee with a stable decision_digest.

New files:
- tests/test_g3_pass_decision_na81.py (NA81 semantics tests)

Updated files:
- tools/node_architect/g3_pass_decision.py (decide_g3_pass_na81)

G3 PASS never grants merge authority; standing pre-prod authority is evaluated
separately. This change is mechanical only -- no autonomous merge / main action.

Parent authority: R10 (issue #232), run SCRUM-288-NA81-RECERT-20260814-R10,
task SCRUM-342. Targets pre-prod only; main is FORBIDDEN.
