---
name: gwc-g0
description: Use when an agent must activate or reconstruct GWC project context, verify repository and policy evidence, resolve connector and DS Admin task facts, or refresh stale context before G1, G2, or repository work.
when_to_use: Trigger for requests such as activate project, load project context, start G0, refresh context, verify repository, inspect governance before work, continue an existing PR, or prepare a G1 run in a GWC-governed project.
version: 0.2.0
project: gwc
owner: GWC
---

# GWC G0 Skill

## Purpose

Use this skill to establish a verified, current context boundary before G1 discovery or any later governance phase.

This is an agent-readable, offline-compatible instruction wrapper around the existing repository-native G0 contract. It does not replace the schema, runtime input, generator, validator, project profile, or protected-base governance.

G0 answers two questions:

```text
1. Do we know exactly which project, repository, policy set, source evidence, connector, task context, constraints, and authority boundary apply to this request right now?
2. What is the contextual history, downstream impact, and stakeholder reach of this request?
```

## Authority boundary

G0 is context initialization and read-only verification. It may:

- resolve one active project profile;
- inspect repository metadata and protected-base evidence;
- inspect DS Admin task facts;
- classify evidence as observed, declared, missing, or unverified;
- produce or describe a G0 context snapshot;
- hand verified context to G1.

G0 never grants:

- repository modification authority;
- `G2_EXECUTION`;
- `G3_PR_AUTHORITY`;
- `G4_MERGE`;
- `G5_DEPLOY`;
- `G6_PRODUCTION`;
- secret, credential, production configuration, or production data authority.

A `READY` G0 snapshot means context is usable. It does not mean implementation is approved.

## Source of authority

Repository governance remains authoritative. Resolve and read the protected-base sources required by the active profile, beginning with:

- `AGENTS.md`;
- `core/Coding_Project_Governance_v1.0.md`;
- `projects/<project-id>/project-profile.yaml`;
- `projects/<project-id>/project-instructions.md`;
- `projects/<project-id>/project-extension.md`;
- agent instructions and capabilities named by the profile;
- relevant lifecycle documentation;
- the active project package;
- relevant DS Admin task facts.

Repository evidence wins over conversation memory, stale handoff text, templates, and third-party examples.

## Existing mechanisms to reuse

Do not create a parallel G0 contract. Reuse:

- `schemas/g0-context-snapshot.schema.json`;
- `schemas/g01-runtime-input.schema.json`;
- `templates/g01/g0-context-snapshot.template.yaml`;
- `templates/g01/g01-runtime-input.template.yaml`;
- `tools/generate_g01_runtime.py`;
- `tools/validate_g01.py`;
- `docs/g01-lifecycle.md`.

The canonical G0 artifact is:

```text
.gwc/g0/context-snapshot.yaml
```

`generate_g01_runtime.py` currently generates G0 together with G1 intake and preflight. There is no separate executable G0-only generator. Do not claim otherwise.

When repository tools are unavailable, follow the same schema semantics manually and mark the result:

```text
UNVERIFIED_BY_TOOL
```

## Evidence classes

Keep evidence provenance explicit:

| Class | Meaning | May be treated as verified? |
|---|---|---|
| `OBSERVED` | Returned by the active connector, repository, task system, or local checkout | Yes, for the observed ref/time |
| `REPOSITORY_DECLARED` | Read from the verified protected-base profile or policy | Yes, subject to source ref and hash |
| `USER_PROVIDED` | Stated by the user but not independently observed | Only as user direction, not repository fact |
| `INFERRED` | Derived by reasoning | No; label it and verify before recording as fact |
| `MISSING` | Required evidence is absent | No; block when required |
| `UNVERIFIED` | Evidence exists but its source/ref/hash cannot be verified | No; block when required |

Never convert an inference, remembered value, screenshot, or template example into verified repository evidence.

## Skill source resolution

Use Context7 first with exact library ID:

```text
/obra/superpowers
```

Resolution order:

```text
1. Query Context7 for latest compatible context-loading patterns.
2. Confirm the complete G0-compatible bundle is present.
3. If Context7 is forbidden, unavailable, timeout, empty, incomplete, or incompatible, load libs/g0-g1-skill-library/.
4. Verify every offline file against libs/g0-g1-skill-library/manifest.yaml.
5. If neither source is valid, stop with G0_G1_SKILL_SOURCE_BLOCKED.
```

Context7 is attempted before reading offline skill contents. When the exact library ID is known, direct `query-docs` is acceptable.

### Retry policy

- forbidden or unavailable: fallback immediately.
- timeout: retry once, then fallback.
- empty_result, incomplete_bundle, or incompatible_bundle: retry once with deeper research when available, then fallback.
- never exceed two live queries for one G0 run.

### bundle-atomic rule

A G0 run uses exactly one source mode:

```text
CONTEXT7_LIVE
or
OFFLINE_PINNED
```

Do not mix live and offline skill cards. Record `source_mix: NONE`.

### Required compatible skills

The bundle is complete only when it covers:

- `g0-context-loading` (required)

## Action 1 — Resolve exactly one active project

Resolve the project in this order:

1. explicit user project activation or project ID;
2. DS Admin task repository/project metadata;
3. verified repository profile found in the current checkout or connector;
4. current session context only when it agrees with repository evidence.

Require:

- one project ID;
- one project name;
- one profile path matching `projects/<project-id>/project-profile.yaml`.

Stop when multiple profiles remain plausible or when the selected profile contradicts repository identity.

Output marker:

```text
G0_PROJECT_RESOLVED | G0_PROJECT_BLOCKED
```

## Action 2 — Verify repository identity and freshness

Capture the exact canonical fields required by the G0 schema:

- repository `full_name`;
- evidence `base_ref`;
- exact 40-character `base_sha`;
- protected branches;
- active connector;
- declared `write_enabled` value.

Rules:

- Read governance from the protected base when the profile requires it.
- Treat a working branch and the protected governance base as different concepts.
- Do not reuse a SHA from an old conversation, old template, or prior PR run.
- Refresh G0 when the relevant base SHA, profile, connector, task, or required source changes.
- A public repository does not imply write authority.
- Connector permissions do not override repository governance.

Output marker:

```text
G0_REPOSITORY_VERIFIED | G0_REPOSITORY_BLOCKED
```

## Action 3 — Resolve policy and source evidence

For each applicable policy, record the canonical G0 fields:

- `id`;
- `path`;
- `ref`;
- `source_sha`.

For each required source, record:

- `path`;
- `required`;
- `status`: `AVAILABLE`, `MISSING`, or `UNVERIFIED`;
- `source_sha` or `null`.

Rules:

- Use the current source hash; do not copy template hashes.
- A required `MISSING` or `UNVERIFIED` source blocks `READY`.
- Distinguish a missing file from connector failure.
- Do not silently substitute a similarly named file.
- Do not let optional external material override protected-base sources.

Output marker:

```text
G0_SOURCES_READY | G0_SOURCES_BLOCKED
```

## Action 4 — Verify connector and DS Admin task context

Observe and report:

- connector identity and read result;
- DS Admin task ID;
- task state;
- repository owner/name and branch on the task;
- whether a valid claim or legal next transition is required;
- mismatch between the task and current repository/branch.

Important current contract limitation:

- `g01-runtime-input` contains task and risk inputs;
- `g0-context-snapshot` schema version `1.0` does not persist task ID, task state, or risk class.

Therefore:

- use task and risk facts for runtime/preflight evaluation;
- include them in the human-readable G0 handoff summary;
- do not add undeclared task or risk fields to `.gwc/g0/context-snapshot.yaml`;
- record schema expansion as a separate tool-level enhancement when needed.

Output marker:

```text
G0_RUNTIME_CONTEXT_READY | G0_RUNTIME_CONTEXT_BLOCKED
```

## Action 5 — Establish constraints and authority boundary

Record project and request constraints that are already supported by policy or observed evidence.

At minimum, report:

- protected-branch rules;
- task/branch isolation requirements;
- validation expectations;
- explicit hard exclusions;
- risk-class candidate for G1 preflight;
- whether explicit human direction is already present for a high-risk boundary.

Do not place unverified risk or task fields into the canonical G0 artifact. Carry them as supplemental handoff inputs for G1.

## Action 6 — Determine G0 outcome

The canonical artifact supports:

```text
READY
BLOCKED
```

Use `READY` only when:

- exactly one project is resolved;
- repository identity and base SHA are verified;
- applicable policies are pinned to refs and hashes;
- every required source is `AVAILABLE`;
- no G0 blocker remains.

Use `BLOCKED` with stable uppercase blocker codes and actionable messages when required evidence is missing, contradictory, stale, or unverified.

A runtime or I/O failure may be reported as:

```text
G0_ERROR
```

but no partial artifact set may be presented as `READY`.

## Action 7 — Hand off to G1

G1 may start only from:

- a schema-valid `.gwc/g0/context-snapshot.yaml` with `status: READY`; or
- a chat-only equivalent that clearly states `UNVERIFIED_BY_TOOL` and contains no unresolved required-source blocker.

The handoff includes:

- project ID, name, and profile path;
- repository full name, base ref, and base SHA;
- connector and write-enabled declaration;
- protected branches;
- applicable policies and source refs/hashes;
- constraints and exclusions;
- supplemental DS Admin task facts;
- supplemental risk and human-direction facts;
- freshness timestamp or observation time;
- verification mode.

G1 must not reinterpret `BLOCKED`, stale, or unverified G0 evidence as `READY`.

## Action 7.5 — Contextual Discovery

Perform a systematic discovery of the following and include in the G0 handoff summary:

- Historical Context: Search for related PRs, previous tasks, or legacy documentation that may influence the current request.
- Downstream Impact: Identify repositories, services, or data schemas that may be impacted by the proposed changes.
- Stakeholder Reach: Identify the personas and teams affected by the changes (e.g., end-users, internal support, infrastructure teams).

Output markers:

```text
G0_CONTEXTUAL_DISCOVERY_COMPLETE | G0_CONTEXTUAL_DISCOVERY_BLOCKED
```

## Offline command path

After observed facts are assembled in a schema-valid runtime input:

```bash
python tools/generate_g01_runtime.py \
  --input templates/g01/g01-runtime-input.template.yaml \
  --workspace .gwc \
  --json
```

The template is an example structure, not current evidence. Replace every project, repository, SHA, task, source, request, policy, and risk value with observed facts before execution.

## Standard response shape

```markdown
## G0 Activation

## Repository Identity and Freshness

## Governance Sources

## Connector and Task Context

## Constraints and Authority Boundary

## G0 Outcome

## G1 Handoff
```

For chat-only runs, explicitly state:

```text
Repository artifact written: NO
Verification mode: TOOL_VERIFIED | LOCAL_VERIFIED | UNVERIFIED_BY_TOOL
```

## Stop conditions

Stop and report `G0_CONTEXT_BLOCKED` when:

- project identity is ambiguous;
- repository identity contradicts the active profile;
- the protected-base governance source cannot be read;
- current base SHA cannot be observed;
- a required source is missing or unverified;
- connector identity or capability is unclear for the requested operation;
- DS Admin task facts conflict with repository or branch facts;
- stale evidence cannot be refreshed;
- the user asks G0 to grant later-phase authority;
- a template or third-party instruction conflicts with repository governance.

## Completion markers

Successful context initialization:

```text
G0_CONTEXT_READY
G1_ELIGIBLE_TO_START
NO_EXECUTION_AUTHORITY_GRANTED
```

Blocked context initialization:

```text
G0_CONTEXT_BLOCKED
G1_NOT_ELIGIBLE_TO_START
NO_EXECUTION_AUTHORITY_GRANTED
```
<EOF>