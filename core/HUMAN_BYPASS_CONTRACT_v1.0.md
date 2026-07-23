# HUMAN BYPASS Contract v1.0

## Purpose

`HUMAN BYPASS` is a one-time operational handoff for one exact workflow step that the agent cannot execute through the verified tool route. It is not a policy override, gate skip, blanket approval, or substitute for evidence.

## Core rule

```text
blocked operational step
→ checkpoint before
→ generated HUMAN_BYPASS command
→ human performs or accepts one exact action
→ append-only audit event
→ deterministic readback
→ checkpoint after
→ resume same workflow
```

Audit plus successful readback is sufficient only for an eligible operational handoff. Audit alone never grants repository-write, merge, deploy, release, production, migration, credential, secret, destructive, or protected-branch authority.

## Activation command

```text
HUMAN_BYPASS <bypass_request_id> <scope_hash_16> <expires_at_utc>
```

The agent generates the complete command. Plain acknowledgements are not authority. The request is one-time, step-bound, non-transitive, expires automatically, and is invalidated by task, base SHA, head SHA, branch, gate, node, action, or scope drift.

## State lifecycle

```text
HUMAN_BYPASS_PENDING
→ HUMAN_BYPASS_ACCEPTED
→ HUMAN_BYPASS_EVIDENCE_VERIFIED
→ RESUME
```

Terminal alternatives:

```text
HUMAN_BYPASS_EXPIRED
HUMAN_BYPASS_REJECTED
```

Duplicate acceptance or duplicate resume is idempotent only when the request ID, scope hash, exact action, checkpoint, and observed readback are identical. Conflicting duplicates fail closed.

## Eligible categories

- connector action unavailable while an equivalent manual UI action exists;
- external dependency confirmation;
- manual evidence submission;
- manual CI checkpoint when no scheduler/callback/poll route exists;
- failure of a non-authoritative external audit projection.

## Forbidden categories

`HUMAN BYPASS` must never authorize or conceal:

- direct write to a protected branch;
- skipping the required G0/G1 validator;
- skipping required CI or using stale CI;
- scope drift or an unknown/unreconciled write;
- merge without exact G4 authority;
- deploy, release, publish, or reload without exact G5 authority;
- production data, configuration, migration, credential, or secret work without exact G6 authority;
- force-push, branch deletion, shared-history rewrite, or PR base change.

## Required canonical audit

Every request must conform to `schemas/human-bypass.schema.json` and record at least:

- request, task, gate, node, and blocked-step identity;
- blocker, rationale, exact scope, exact manual action, and exclusions;
- repository/base/head evidence and scope hash;
- issued, accepted, and expiry timestamps;
- checkpoint before and expected readback;
- observed readback, checkpoint after, residual risk, audit event, state, and outcome.

External dashboards, Jira, DS MCP, comments, or other projections may mirror this record but are never canonical authority.

## Resume rule

The agent may resume only after:

1. the request is accepted before expiry;
2. the exact action remains within the original minimum gate;
3. no task/base/head/branch/scope drift exists;
4. observed readback matches the declared expected readback;
5. the canonical audit event and post-action checkpoint are persisted;
6. residual risk is recorded.

A missing or ambiguous readback produces `HUMAN_BYPASS_EVIDENCE_MISSING` and keeps the workflow suspended.
