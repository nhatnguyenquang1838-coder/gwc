
---
extension_id: pm-skills-conventions
version: "1.0"
authoritative: false
extends_profile: pm-skills
core_policy: CODING-PROJECT-GOVERNANCE@1.0
core_sha256: ea3e44ac2d948b8439e9768bea4f5dda8474a34e914592130965083792a5ee48
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
