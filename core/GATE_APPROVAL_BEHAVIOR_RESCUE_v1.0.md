---
spec_id: GATE-APPROVAL-BEHAVIOR-RESCUE
version: "1.0"
status: rescue_draft
authoritative_after_merge: true
language: en
policy_scope: gwc_gate_behavior
approval_protocol: write-gates-only
policy_source: this_file
---

# Gate Approval Behavior Rescue v1.0

## Purpose

This rescue amendment changes GWC gate behavior so approval envelopes are required only for gates that can perform writes or external state changes.

It preserves the G0 → G1 → G2 → G3 → G4 → G5 → G6 lifecycle, but changes which gates require human approval envelopes.

## Rule summary

```text
G0_CONTEXT   = intake/context/read-only; no approval envelope required
G1_ALIGNMENT = planning/alignment/read-only; no approval envelope required
G2_EXECUTION = implementation/write/state-change; approval envelope required
G3_PR        = Draft PR creation/update; approval envelope required
G4_MERGE     = merge/auto-merge; approval envelope required
G5_DEPLOY    = deploy/release; approval envelope required
G6_PROD      = production data/config/migration/secrets; approval envelope required
```

## Definitions

- `approval envelope`: a scoped, hash-bound, expiring approval package that the user grants by exact command.
- `write-capable action`: any connector/tool action that creates, updates, deletes, commits, pushes, opens/updates a PR, merges, deploys, changes config, accesses secrets, or mutates/reads production data where policy requires a production gate.
- `read-only planning`: inspection, intake, evidence collection, option analysis, risk analysis, acceptance criteria, scope drafting, and local artifact preparation that does not mutate repository or remote state.

## G0 behavior

G0 is an intake/context gate.

Permitted without approval envelope:

- read repository governance and task context;
- read connector metadata;
- inspect files, CI, issues, PRs, and docs;
- create local `/mnt` evidence artifacts;
- produce Intake Card and G0 context snapshot;
- identify blockers and required next gate.

Not permitted in G0:

- repository writes;
- branch creation;
- commits or pushes;
- PR mutation;
- merge/deploy/release;
- production data/config/secrets/migration actions.

## G1 behavior

G1 is a planning/alignment gate.

Permitted without approval envelope:

- create and validate planning artifacts;
- create G1 intake, preflight, options, and decision records;
- run local/read-only validators;
- draft execution scope;
- generate the G2 approval envelope proactively.

G1 remains evidence-gated. A user saying `ok`, `continue`, or similar does not make G1 pass. G1 passes only when required artifacts and validator evidence pass for the current execution mode.

Not permitted in G1:

- repository writes;
- branch creation;
- commits or pushes;
- PR mutation;
- merge/deploy/release;
- production data/config/secrets/migration actions.

## G2 behavior

G2 is the first write-capable execution gate.

G2 requires an approval envelope before any write-capable action, including:

- guarded branch/worktree creation;
- repository file creation/update/deletion;
- commit creation;
- push/update ref;
- non-production external state mutation;
- sandboxed validation that executes repository-controlled code, when policy treats such execution as gated.

G2 does not authorize:

- Draft PR creation unless explicitly included and not reserved to G3 by active project policy;
- merge;
- deploy/release;
- production data/config/secrets/migration actions;
- protected branch direct write;
- force-push, branch deletion, shared-history rewrite, or PR base change.

## G3 behavior

G3 owns Draft PR delivery.

G3 requires its own scoped approval envelope before creating or updating a Draft PR, unless the active project policy explicitly allows Draft PR creation within the same G2 envelope.

G3 does not authorize merge, deploy, release, production data/config/secrets/migration actions, or making a Draft PR ready for review unless explicitly authorized by policy.

## G4 behavior

G4 owns merge and auto-merge.

G4 always requires a separate approval envelope bound to the exact PR, repository, base branch, head SHA, scope hash, merge method, and expiry.

## G5 behavior

G5 owns deploy and release.

G5 always requires a separate approval envelope bound to the exact environment, release/commit, action, rollback expectation, and expiry.

## G6 behavior

G6 owns production data, production configuration, migrations, credentials, secrets, and destructive production operations.

G6 always requires a separate approval envelope. No earlier gate can grant G6 authority.

## Exact command format

Only write-capable gates require exact approval commands.

Canonical format:

```text
APPROVE <GATE> <approval_request_id> <scope_hash_16> <expires_at_utc>
```

Allowed gates for approval envelopes:

```text
G2
G3
G4
G5
G6
```

G0 and G1 must not request or require approval envelopes.

## Runtime enforcement

Before invoking a write-capable tool or connector action, the agent must:

1. Map the action to G2/G3/G4/G5/G6.
2. Verify current gate artifacts and validator evidence.
3. Verify the matching approval envelope.
4. Confirm repository, branch, base SHA, files write, authorized actions, excluded actions, scope hash, and expiry.
5. Stop fail-closed on mismatch.

Read-only inspection and planning must not be blocked merely because no approval envelope exists for G0 or G1.

## Compatibility

This amendment is intended to supersede any older wording that required an approval envelope or human approval for G0 intake or G1 planning.

It does not weaken:

- evidence requirements;
- validator requirements;
- write scope discipline;
- protected branch safety;
- separate G4/G5/G6 authority;
- secrets and production-data protections;
- validation honesty;
- hard-stop exclusions.

## Migration notes

Required follow-up edits:

- `AGENTS.md` should include this file in authority order above legacy gate wording.
- `core/Agent_Operating_Runtime_Contract_v1.0.md` should state that only G2-G6 generate approval envelopes.
- `core/Coding_Project_Governance_v1.0.md` should replace G1 inspect approval semantics with read-only G0/G1 no-envelope semantics.
- `core/GATE_LIFECYCLE_CONTRACT_v1.0.md` should clarify that proactive approval generation starts at G1 exit for G2 only, not for G0/G1 entry.
- Validators and tests should reject approval envelopes for G0/G1 and require them for write-capable G2-G6 gates.
