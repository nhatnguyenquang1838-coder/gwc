# SCRUM-615 G3 External PR-Tip Binding Design

## Problem

G3 currently requires the committed task-scoped `g3/delivery-record.yaml`, validation, review and CI evidence to match the exact current PR head. Committing the record changes that head, so the record can never durably embed the SHA of its own containing commit. Rewriting the record produces an infinite self-reference loop.

## Decision

Adopt Option A: **subject/container separation**.

- The committed delivery record binds the immutable **implementation subject**.
- The exact **current PR tip/container** is supplied by trusted runtime at validation time and is not a required field inside the committed record.
- The validator proves the implementation subject is an ancestor of or equal to the current PR tip.
- The aggregate delta from implementation subject to current PR tip must contain only explicitly allowed G3 evidence paths.
- Exact-tip CI is supplied/verified externally. A committed delivery record may declare required check names but must not claim a self-referential current-tip SHA/status.
- Any implementation, test, workflow, runtime, configuration or other non-evidence mutation after the implementation subject fails closed and returns to G2.

## Identity model

1. `implementation_head_sha`: immutable implementation commit reviewed and locally/applicably validated.
2. `implementation_scope_hash`: scope identity for that implementation subject.
3. `current_pr_head`: trusted external runtime fact.
4. `evidence_delta_paths`: trusted external aggregate changed-path set for `implementation_head_sha..current_pr_head`.
5. current-tip CI results: trusted external runtime evidence.

The delivery record never embeds a mandatory `evidence_tip_sha` or equivalent self-reference.

## Runtime validation contract

For an active v1.1 G3 pass, `tools/validate_g3_delivery.py` receives:

- `--current-pr-head <40-hex-sha>`;
- an explicit assertion that ancestry was verified by trusted repository/runtime evidence;
- zero or more evidence-delta paths;
- current-tip CI check results for required checks.

The validator fails closed when the current PR head is absent, ancestry is not verified, a delta path is outside the evidence allowlist, or a required current-tip CI check does not pass.

Default evidence allowlist is task-scoped G3 evidence only:

- `.gwc/tasks/<task-id>/g3/**`

No source, tests, workflow, dependency, runtime, configuration or unrelated governance file is allowed in the post-implementation evidence delta.

## Record schema v1.1

The canonical template moves from v1.0 to v1.1.

- top-level `head_sha` becomes `implementation_head_sha`;
- `validation.head_sha` becomes `validation.implementation_head_sha`;
- `review.reviewed_head_sha` becomes `review.reviewed_implementation_head_sha`;
- accepted-risk evidence binds `implementation_head_sha`;
- committed `ci` declares required check names only; current-tip results are external runtime evidence.

## Legacy compatibility

Existing committed v1.0 records are immutable historical evidence and are not silently reinterpreted. They may be read as legacy provenance, but an **active** G3 closure under the repaired contract must materialize/migrate a v1.1 record and rerun G3 validation/review against the implementation subject plus external current-tip runtime evidence.

No historical v1.0 record is rewritten automatically.

## G3 semantics

An evidence-only current-tip change invalidates/recomputes tip-level evidence (CI, ancestry and evidence delta) but does **not** invalidate implementation validation/review when the implementation subject and scope are unchanged.

Any non-evidence current-tip delta invalidates the implementation binding and returns to G2.

## Regression case

SCRUM-397 must be representable without recursion:

- implementation subject: `4e0989cf0770637eabc90c20fa6757fb4f1f4089`;
- evidence-containing PR tip: `5437b7f20edfcb7b717e1b7b78d9514985927d7b`;
- implementation subject is verified ancestor;
- aggregate post-implementation delta is evidence-only;
- required CI passes at the external current PR tip.

No follow-up commit is required merely to rewrite the tip SHA into the record.

## Scope

Primary executable surfaces:

- `schemas/g3-delivery-record.schema.json`
- `templates/gates/g3-delivery-record.template.yaml`
- `tools/validate_g3_delivery.py`
- `tests/test_g3_delivery.py`
- `skills/gwc-g3/SKILL.md`
- `projects/gwc/project-instructions.md`
- `projects/gwc/project-extension.md`
- `core/E2E_DRAFT_PR_DELIVERY_RULE.md` only where it defines conflicting G3 artifact semantics.

No SCRUM-397 delivery-branch mutation is part of SCRUM-615.

## Authority boundary

This hotfix may produce a validated Draft PR. G4 merge remains a separate Human decision. No protected-main write, auto-merge, deploy, release, production configuration/data, credential, migration or history-rewrite authority is granted.