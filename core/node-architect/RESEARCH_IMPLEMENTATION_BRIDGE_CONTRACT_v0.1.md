# Node Architect Research → Implementation Bridge Contract v0.1

## Purpose

This contract turns a completed S2 four-lens Node Architect research review into a governed implementation-planning candidate without conflating research validity, Human review, implementation planning, G2 execution authority, or G4 merge authority.

It extends the existing GWC lifecycle; it does **not** add a new GWC gate.

## State machine

```text
FOUR_LENS_REVIEW_COMPLETE + 4/4 APPROVE
  -> RESEARCH_CANDIDATE_VALID
  -> implementation validation against exact current protected main
     -> RESEARCH_VALIDATED
     -> RESEARCH_VALIDATED_WITH_AMENDMENTS
     -> RESEARCH_STALE_REVIEW_REQUIRED
     -> RESEARCH_INVALIDATED
     -> AGENT_PREPARATION_BLOCKED

RESEARCH_VALIDATED | RESEARCH_VALIDATED_WITH_AMENDMENTS
  -> HUMAN_REVIEW_REQUIRED
  -> exact Human approval bound to current scope hash
  -> HUMAN_REVIEW_APPROVED
  -> IMPLEMENTATION_PLAN_READY
  -> AWAITING_G2_AUTHORITY
  -> normal GWC G0/G1/G2 implementation lifecycle
```

`RESEARCH_STALE_REVIEW_REQUIRED`, `RESEARCH_INVALIDATED`, and `AGENT_PREPARATION_BLOCKED` do not request Human planning approval. They return to research/remediation/materialization as appropriate.

## Eligibility and dependency safety

1. All four durable lens verdicts must be `APPROVE` before a record may enter `HUMAN_REVIEW_REQUIRED`.
2. Jira status is projection only. `Done` never proves delivery by itself.
3. A dependency reported `Done` without durable deliverable evidence is `DONE_EVIDENCE_UNSAFE` and blocks the bridge from claiming dependency satisfaction.
4. A semantically Cancelled, Superseded, refinement-only, abandoned, no-deliverable, contradictory, or unbound `Done` item is unsafe dependency evidence.

## Implementation validation

Validation is bound to the exact protected `main` SHA current at validation time, not only the S1 snapshot SHA. The validator must compare the research recommendation and assumptions with current repository/governance surfaces and record:

- research parent and paired GitHub issue;
- S1 snapshot SHA and exact current-main SHA;
- all four durable lens verdicts;
- final validated recommendation;
- amendments;
- implementation surfaces;
- risks and acceptance criteria;
- dependencies and deliverable-evidence safety;
- deterministic `HUMAN_REVIEW_SCOPE_HASH`.

The machine schema is `schemas/node-architect/research-implementation-validation.schema.json` and the semantic validator is `tools/validate_research_implementation_bridge.py`.

## Deterministic Human-review scope hash

The canonical hash input is JSON encoded with UTF-8, sorted keys, and compact separators over exactly:

```text
research_parent
paired_github_issue
s1_snapshot_sha
current_main_sha
four_lens_verdicts
final_validated_recommendation
amendments
implementation_surfaces
risks
acceptance_criteria
```

The output is `sha256:<64 lowercase hex>`.

Any material change to these fields produces a new hash and invalidates an unconsumed approval candidate.

## Human review authority

When validation is `RESEARCH_VALIDATED` or `RESEARCH_VALIDATED_WITH_AMENDMENTS`, S2 must publish `HUMAN_REVIEW_REQUIRED` and stop before implementation planning.

The only accepted planning-approval command is:

```text
APPROVE RESEARCH_PLAN <PARENT_KEY>-<YYYYMMDD>-R<n> <FIRST_16_HEX_OF_SCOPE_HASH>
```

Vague acknowledgements such as `ok`, `approve`, `continue`, reactions, Jira status, bot messages, or a command bound to a different run/hash are not authority.

This approval authorizes **only** materialization of the implementation plan. It does not grant G2 execution, G4 merge, deployment, release, production/config/data/secret/migration authority.

If current `main` materially changes before approval consumption, validation and the approval candidate must be refreshed.

## Implementation-plan contract

Only a verified `HUMAN_REVIEW_APPROVED` state may produce an `IMPLEMENTATION_PLAN`.

The plan must contain:

- target repository and exact planning-base SHA;
- objective and non-goals;
- requirement-to-change mapping;
- 3–7 atomic work packages;
- explicit DAG dependencies and safe parallelism;
- migration/backward-compatibility considerations where applicable;
- test matrix;
- observability and rollback;
- acceptance criteria and risk register;
- expected PR slicing/integration order;
- normal GWC gate path `G0 -> G1 -> G2 -> G3 -> G4 -> G5`, plus `G6` only when applicable;
- required evidence/ownership assumptions in the durable plan projection;
- an implementation scope hash.

The terminal planning state is:

```text
IMPLEMENTATION_PLAN_READY
AWAITING_G2_AUTHORITY
```

The plan must set `grants_execution_authority: false`.

## Projection contract

### Repository / GitHub

Repository evidence is technical authority. The paired GitHub research issue receives substantive validation and plan projections, including exact SHAs and hashes. Repository contract/schema/validator behavior controls when projection text conflicts with machine evidence.

### Jira

Jira remains planning/status/claim projection. Store durable state markers and links, but never infer research validity or G2 authority from Jira status alone.

### Slack

Reuse exactly one canonical root thread for the research parent. Post validation classification, compact review packet, exact approval command, approval receipt, and implementation-plan readiness into the same thread. Slack messages communicate authority only when the Human's exact command is attributable, current, hash-bound, and read back.

## S2 idempotency

- Never redo completed L1–L4 merely because a parent is awaiting Human review or planning.
- A post-L4 validation or plan materialization counts as the one S2 work unit for that tick.
- Repeated projection must not create duplicate canonical Slack roots or duplicate plans for the same scope hash.
- New material main/research drift creates a new validation/hash/revision rather than mutating historical evidence in place.

## Validation examples

```bash
python tools/validate_research_implementation_bridge.py validation \
  --record implementation-validation.yaml \
  --current-main-sha <40-hex-sha>

python tools/validate_research_implementation_bridge.py approval \
  --command 'APPROVE RESEARCH_PLAN SCRUM-500-20260823-R1 0123456789abcdef' \
  --run-id SCRUM-500-20260823-R1 \
  --scope-hash sha256:<64-hex>

python tools/validate_research_implementation_bridge.py plan \
  --record implementation-plan.yaml
```
