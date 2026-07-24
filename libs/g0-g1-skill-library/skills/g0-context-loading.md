# G0 Context Loading

## Purpose

Use this skill to activate or reconstruct GWC project context, verify repository and policy evidence, resolve connector and DS Admin task facts, and refresh stale context before G1 or any later governance phase.

## When to use

- activate project
- load project context
- start G0
- refresh context
- verify repository
- inspect governance before work
- continue an existing PR
- prepare a G1 run

## Source resolution

Query Context7 first with library ID `/obra/superpowers` for the latest compatible context-loading patterns.

Resolution order:
1. Query Context7 for latest compatible guidance.
2. If Context7 is forbidden, unavailable, timeout, empty, incomplete, or incompatible, load this pinned offline card.
3. Verify the offline file against `libs/g0-g1-skill-library/manifest.yaml`.
4. If neither source is valid, stop with `G0_G1_SKILL_SOURCE_BLOCKED`.

Retry policy:
- forbidden or unavailable: fallback immediately.
- timeout: retry once, then fallback.
- empty/incomplete/incompatible: retry once with deeper research when available, then fallback.
- never exceed two live queries for one G0 run.

## Scope

This skill covers:
- resolving exactly one active project profile;
- verifying repository identity and protected base SHA;
- resolving applicable governance sources and their hashes;
- verifying connector identity and write-enabled declaration;
- classifying evidence as OBSERVED, REPOSITORY_DECLARED, USER_PROVIDED, INFERRED, MISSING, or UNVERIFIED;
- producing or describing a G0 context snapshot;
- handing verified context to G1.

This skill does not grant repository modification authority, G2_EXECUTION, G3_PR_AUTHORITY, G4_MERGE, G5_DEPLOY, G6_PRODUCTION, or any secret/credential/production-data authority.

## Evidence markers

Use explicit outcome markers:
- G0_PROJECT_RESOLVED
- G0_PROJECT_BLOCKED
- G0_REPOSITORY_VERIFIED
- G0_REPOSITORY_BLOCKED
- G0_SOURCES_READY
- G0_SOURCES_BLOCKED
- G0_RUNTIME_CONTEXT_READY
- G0_RUNTIME_CONTEXT_BLOCKED
- G0_CONTEXTUAL_DISCOVERY_COMPLETE
- G0_CONTEXTUAL_DISCOVERY_BLOCKED

## Stop conditions

Stop and report G0_CONTEXT_BLOCKED when:
- project identity is ambiguous;
- repository identity contradicts the active profile;
- protected-base governance source cannot be read;
- current base SHA cannot be observed;
- a required source is missing or unverified;
- connector identity or capability is unclear;
- DS Admin task facts conflict with repository or branch facts;
- stale evidence cannot be refreshed;
- the user asks G0 to grant later-phase authority;
- a template or third-party instruction conflicts with repository governance.