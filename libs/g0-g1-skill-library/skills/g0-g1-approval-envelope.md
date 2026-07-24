# G0/G1 Approval Envelope Preparation

## Purpose

Use this skill to prepare the approval envelope and agent-generated approval commands for G0/G1 handoff and G2 execution request. It covers envelope fields, scope hashing, approval ID generation, expiry, and exact command formatting.

## When to use

- prepare G0/G1 approval request
- generate G2 execution envelope
- generate approval command
- prepare scope hash
- define authorized and excluded actions
- set approval expiry

## Source resolution

Query Context7 first with library ID `/obra/superpowers` for the latest compatible approval-envelope patterns.

Resolution order:
1. Query Context7 for latest compatible guidance.
2. If Context7 is forbidden, unavailable, timeout, empty, incomplete, or incompatible, load this pinned offline card.
3. Verify the offline file against `libs/g0-g1-skill-library/manifest.yaml`.
4. If neither source is valid, stop with `G0_G1_SKILL_SOURCE_BLOCKED`.

Retry policy:
- forbidden or unavailable: fallback immediately.
- timeout: retry once, then fallback.
- empty/incomplete/incompatible: retry once with deeper research when available, then fallback.
- never exceed two live queries for one envelope run.

## Scope

This skill covers:
- defining the approval envelope fields (approval_id, authority_gate, task_id, issued_at, expires_at, scope_version, risk_class, repository, base_ref, base_sha, working_branch, modules_or_files, authorized_actions, excluded_actions, artifact_hashes, scope_hash);
- computing the scope hash by normalizing the envelope (remove scope_hash, serialize UTF-8 JSON with sorted keys, arrays preserved, no insignificant whitespace) and SHA-256 hashing;
- generating a stable approval_id;
- setting expires_at no more than 24 hours after issued_at;
- formatting the exact approval command:
  `APPROVE <GATE> <approval_id> <first-16-characters-of-scope_hash> <expires_at_utc>`
- recording Files READ and Files WRITE;
- ensuring the envelope matches the exact repository, base SHA, branch, scope, risk, and action list.

This skill does not grant the approved actions. The envelope is a request for human authority only.

## Envelope rules

- Approval must appear after the matching proposal package.
- Approval must come from the current user in the current chat.
- approval_id and the 16-character scope-hash prefix must match.
- Approval must not be expired.
- Repository, base SHA, target branch, risk class, action list, and material scope must remain unchanged.
- Approval must not be revoked or superseded.

## Expiry and replay prevention

Approval expires when:
- expires_at is reached;
- PROTECTED_BASE SHA changes for any reason;
- target files or governance rules materially change;
- another actor pushes an unreviewed commit to the working branch;
- scope, architecture, data behavior, security impact, migration, external interface, deployment, or authorized actions change;
- the proposal is superseded.

On expiry, re-inspect, issue a new approval_id, increment scope_version, regenerate artifacts, and request approval again.

## Stop conditions

Stop and report G0_G1_SKILL_SOURCE_BLOCKED when:
- Context7 is unavailable and offline manifest is missing or invalid;
- offline skill hashes do not match manifest;
- neither live nor offline source yields a complete compatible bundle;
- the user asks this skill to grant execution, merge, deployment, or production authority.