# P5 Evaluation and Controlled Self-Improvement Contract v0.1

## Authority model

GWC remains authoritative for gates and exact approval envelopes. GitHub remains authoritative for repository refs, PR heads, merge commits and CI. Jira, Slack and Notion remain projection layers and cannot grant gate authority.

## Evaluation boundary

The SCRUM-122 through SCRUM-126 chain is a no-production evaluation package. It may create task-scoped repository artifacts, validators, examples, a guarded branch and a Draft PR. It must not deploy, release, publish, mutate production data or configuration, access secrets, run migrations, perform destructive actions, force-push, delete branches, change PR bases, or auto-merge.

## Required metric families

The record MUST carry metrics for:

- planning completeness and planning evidence freshness;
- runtime history completeness and checkpoint/replay fidelity;
- outcome comparison accuracy and recovery success;
- catalog quality, including missing and redundant node coverage;
- route-selection accuracy, human override rate, evidence completeness, escaped defects and policy-violation rate;
- confidence calibration for the shadow planner.

## Required guards

- version-bound artifacts;
- exact base SHA binding;
- checkpoint and replay readback;
- stable idempotency keys for side effects;
- shadow no-side-effect operation for ineligible routes;
- bounded canary eligibility and allowlist checks;
- human approval for promotion;
- stable fallback when candidate confidence is insufficient;
- projection authority denial for Jira, Slack and Notion.

## Promotion lifecycle

experimental -> candidate -> pilot -> stable -> deprecated -> retired

Automatic promotion is not allowed. Human review and rollback planning are required before any stage advance.

## Required failure codes

- STALE_ARTIFACT
- DUPLICATE_SIDE_EFFECT
- REPLAY_DIVERGENCE
- PROJECTION_AUTHORITY_LEAKAGE
- SHADOW_SIDE_EFFECT
- CANARY_POLICY_VIOLATION
- CONFIDENCE_CALIBRATION_DRIFT
- PROMOTION_POLICY_VIOLATION
- G6_REQUIRED

