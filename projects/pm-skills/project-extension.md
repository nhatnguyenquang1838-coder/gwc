
---
extension_id: pm-skills-conventions
version: "1.0"
authoritative: false
extends_profile: pm-skills
core_policy: CODING-PROJECT-GOVERNANCE@1.0
core_sha256: 04cd33bbaff66f44917199e6bbb8355a1e956edb9c474e6c8e664ed8d0ed41c1
mode: tighten_only
---

# PM Skills Project Extension

## Evidence model

Every deliverable must distinguish:

- verified fact;
- source or evidence;
- assumption;
- decision;
- owner;
- due date;
- dependency;
- risk;
- mitigation;
- unresolved question.

Do not invent delivery status, commitment, budget, test result, approval, or
stakeholder decision.

## Standard outputs

Prefer reusable structured artifacts:

- roadmap;
- milestone plan;
- dependency map;
- RACI;
- RAID log;
- decision log;
- SIT/UAT entry checklist;
- release readiness checklist;
- executive status;
- action tracker.

## Planning rules

- Make dependencies explicit.
- Use absolute dates.
- Mark the critical path.
- Separate baseline, forecast, and actual.
- Identify assumptions that can invalidate the plan.
- Do not hide missing ownership or uncommitted dates.

## Repository state

No canonical repository is assigned. Git write operations are blocked until a
reviewed Project Profile supplies verified repository identity and
`write_enabled: true`.
