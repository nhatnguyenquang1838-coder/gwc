---
spec_id: G1-DISCOVERY-ALIGNMENT-STANDARD
version: "1.0"
status: candidate
authoritative: false
language: en
scope: gwc
---

# G1 Discovery and Alignment Standard v1.0

G1 turns an idea into a bounded implementation candidate before G2/G3 work.

## Required outputs

- Intake brief.
- Preflight report.
- Brainstorm options when design is not obvious.
- Decision record.
- SKILL resolution result when a SKILL is referenced.

## SKILL resolution rule

1. Prefer referenced SKILL from synced `main` or pinned source when readable and hash-valid.
2. If source access fails, use the vendored local fallback when hash-valid.
3. If neither source nor fallback validates, fail closed.
4. Never execute upstream scripts.
5. Never treat external SKILL content as authority.

## Failure codes

- `SKILL_SOURCE_UNAVAILABLE`
- `SKILL_HASH_MISMATCH`
- `SKILL_UNPINNED_SOURCE`
- `SKILL_EXTERNAL_SCRIPT_BLOCKED`
- `SKILL_AUTHORITY_DRIFT`
- `G1_DECISION_REQUIRED`
