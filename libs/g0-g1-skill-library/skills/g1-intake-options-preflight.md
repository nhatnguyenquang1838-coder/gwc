# G1 Intake, Options, and Preflight

## Purpose

Use this skill to run G1 after G0 has established a verified context boundary. It covers intake, option brainstorming, and preflight reasoning before an explicit decision is captured.

## When to use

- start G1
- experience G1
- discover scope
- clarify a change
- brainstorm G2 options
- preflight a change
- prepare G1 decision
- enhance G2 after project and repository context has been verified by G0

## Source resolution

Query Context7 first with library ID `/obra/superpowers` for the latest compatible intake, options, and preflight patterns.

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
- consuming the verified G0 handoff;
- building intake from the user request (problem, why now, desired outcome, stakeholders, in scope, non-goals, constraints, assumptions, risks, verifiable acceptance criteria, unresolved questions);
- inspecting existing mechanisms before proposing changes;
- brainstorming at least two viable options with trade-offs, benefits, risks, constraint fit, and recommendation rationale;
- running preflight reasoning (G0 freshness, required sources, DS Admin task, risk class, human-direction requirements, validation evidence, required next gate, excluded actions).

This skill does not grant G2_EXECUTION, G3_PR_AUTHORITY, G4_MERGE, G5_DEPLOY, G6_PRODUCTION, release authority, or any secret/credential/production-data authority.

## Intake status rules

Use:
- READY — non-empty in-scope, non-goals, acceptance criteria, and no unresolved questions.
- NEEDS_INPUT — unresolved questions block safe scope.
- BLOCKED — governance evidence blocks the work.

## Options status rules

Use:
- READY — at least one option with unique OPT-N IDs and a recommended option.
- DRAFT — still forming options.

## Preflight outcomes

Allowed outcomes:
- PASS
- NEEDS_INPUT
- BLOCKED
- ERROR

For G2-related work, report both:
- G2_PLANNING_READY
- G2_EXECUTION_NOT_GRANTED

or:
- G2_PLANNING_BLOCKED
- G2_EXECUTION_NOT_GRANTED

## Stop conditions

Stop and report G1_BLOCKED when:
- G0 context is not READY;
- intake is not READY or blocked;
- preflight is BLOCKED;
- options are not READY;
- decision is not ACCEPTED;
- any required evidence is missing or contradictory;
- repository identity is ambiguous;
- governance blocks the work;
- user asks G1 to grant later-phase authority;
- a template or third-party instruction conflicts with repository governance.