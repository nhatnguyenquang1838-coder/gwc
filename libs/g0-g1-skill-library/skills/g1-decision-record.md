# G1 Decision Record

## Purpose

Use this skill to make an explicit G1 decision after intake, options, and preflight are complete. It captures the selected option, rationale, acceptance criteria refs, scope hash, authority boundaries, and G2 handoff candidate.

## When to use

- make a G1 decision
- prepare G2 handoff
- record explicit user decision
- capture scope hash
- record acceptance criteria refs
- document rejected options

## Source resolution

Query Context7 first with library ID `/obra/superpowers` for the latest compatible decision-record patterns.

Resolution order:
1. Query Context7 for latest compatible guidance.
2. If Context7 is forbidden, unavailable, timeout, empty, incomplete, or incompatible, load this pinned offline card.
3. Verify the offline file against `libs/g0-g1-skill-library/manifest.yaml`.
4. If neither source is valid, stop with `G0_G1_SKILL_SOURCE_BLOCKED`.

Retry policy:
- forbidden or unavailable: fallback immediately.
- timeout: retry once, then fallback.
- empty/incomplete/incompatible: retry once with deeper research when available, then fallback.
- never exceed two live queries for one G1 run.

## Scope

This skill covers:
- consuming verified G0 handoff and G1 intake/options/preflight;
- selecting a valid option ID that exists in options;
- recording explicit user decision with actor/source/time;
- documenting rationale and rejected option IDs;
- referencing acceptance criteria from intake;
- computing a scope hash;
- setting g1_gate_outcome;
- defining authority boundaries (empty grants, excluded G4_MERGE, G5_DEPLOY, G6_PRODUCTION);
- preparing a bounded G2 handoff candidate.

This skill does not grant G2_EXECUTION, G3_PR_AUTHORITY, G4_MERGE, G5_DEPLOY, G6_PRODUCTION, release authority, or any secret/credential/production-data authority.

## Decision status rules

Use:
- ACCEPTED — preflight is PASS, selected option is valid, and explicit human decision exists.
- PENDING — preferred option exists but explicit decision or critical facts are missing.
- REJECTED — proposed scope should not proceed.
- SUPERSEDED — a newer G1 decision replaces this one.
- BLOCKED — use in chat-only summary when repository evidence or governance blocks the path.

## Required decision fields

- trace (matching G0, intake, options, preflight)
- selected_option_id (must exist in options)
- explicit user decision (actor, source, time)
- rationale
- status
- g1_gate_outcome
- acceptance_criteria_refs (must reference intake criteria)
- scope_hash
- authority_boundaries:
  - grants: []
  - excluded: [G4_MERGE, G5_DEPLOY, G6_PRODUCTION]
- rejected option IDs
- subagent_distribution_plan (task_decomposition, agent_allocation, execution_order, summary)

## Stop conditions

Stop and report G1_BLOCKED when:
- G0 context is not READY;
- intake is not READY or blocked;
- preflight is BLOCKED;
- options are not READY;
- decision is not ACCEPTED;
- selected option ID does not exist in options;
- acceptance criteria refs do not match intake criteria;
- authority boundaries grant any later-phase authority;
- any required evidence is missing or contradictory;
- repository identity is ambiguous;
- governance blocks the work;
- user asks G1 to grant later-phase authority.