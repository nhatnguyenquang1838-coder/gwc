# G3 External PR-Tip Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove G3 delivery-record self-reference by separating implementation-subject evidence from externally verified current PR-tip evidence.

**Architecture:** The committed v1.1 delivery record binds `implementation_head_sha` and implementation scope only. `validate_g3_delivery.py` receives current PR head, verified ancestry, evidence-delta paths, and current-tip CI results from trusted runtime and fails closed on non-evidence drift or missing CI. Historical v1.0 records remain immutable provenance and active G3 closures migrate to v1.1.

**Tech Stack:** Python 3, unittest, JSON Schema Draft 2020-12, YAML, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-28-g3-external-pr-tip-binding-design.md`

## Global Constraints

- Base: `main@bad63d466f3d1e40ee5184d75551c3abaa2f0617`.
- Branch: `hotfix/scrum-615-g3-external-pr-tip-binding`.
- Jira: `SCRUM-615`; paired GitHub issue: `#528`.
- Do not mutate SCRUM-397 delivery branch or PR #525.
- G4 merge remains separate Human authority.
- No `evidence_tip_sha` or equivalent self-referential container SHA in committed v1.1 record.
- Post-implementation delta allowlist defaults to `.gwc/tasks/<task-id>/g3/**` only.

---

### Task 1: RED contract tests

**Files:**
- Modify: `tests/test_g3_delivery.py`

**Interfaces:**
- Consumes: current `validate_record(record, schema)` behavior.
- Produces: failing tests defining v1.1 implementation-subject semantics and external current-tip validation API.

- [ ] Add a v1.1 record fixture derived from the template using `implementation_head_sha`, `validation.implementation_head_sha`, `review.reviewed_implementation_head_sha`, and required CI check names without embedded current-tip SHA.
- [ ] Add RED test: a valid v1.1 record is structurally accepted by `validate_record`.
- [ ] Add RED test: active `outcome=pass` runtime validation fails when `current_pr_head` is missing.
- [ ] Add RED test: implementation subject plus a different current PR tip passes when ancestry is verified, all delta paths are task-scoped G3 evidence, and required external CI checks pass.
- [ ] Add RED test: non-evidence delta path such as `src/example.py` fails closed.
- [ ] Add RED test: unverified ancestry fails closed.
- [ ] Add RED test: missing/failing required current-tip CI fails closed.
- [ ] Add RED test: legacy v1.0 is explicitly rejected for new active G3 closure rather than silently reinterpreted.
- [ ] Push RED commit and verify `Validate instructions` fails for the expected new-contract assertions.

### Task 2: Schema and template v1.1

**Files:**
- Modify: `schemas/g3-delivery-record.schema.json`
- Modify: `templates/gates/g3-delivery-record.template.yaml`

**Interfaces:**
- Produces canonical v1.1 record fields used by validator/tests.

- [ ] Set canonical schema/template version to `1.1`.
- [ ] Replace top-level `head_sha` with `implementation_head_sha`.
- [ ] Replace validation/review head bindings with implementation-subject names.
- [ ] Bind accepted-risk evidence to implementation subject.
- [ ] Replace committed CI `head_sha` + status-bearing checks with required check declarations that do not claim current-tip state.
- [ ] Preserve all seven review lanes and later-gate exclusions.

### Task 3: Runtime-context semantic validator

**Files:**
- Modify: `tools/validate_g3_delivery.py`

**Interfaces:**
- Keep: `validate_record(record, schema) -> list[str]` for structural/subject semantics.
- Add: `validate_runtime_context(record, *, current_pr_head, implementation_ancestor_verified, evidence_delta_paths, ci_checks) -> list[str]`.
- CLI adds: `--current-pr-head`, `--implementation-ancestor-verified`, repeated `--evidence-delta-path`, repeated `--ci-check NAME=STATUS`.

- [ ] Make semantic implementation bindings compare validation/review/risk acceptance against `implementation_head_sha`.
- [ ] Add task-scoped evidence-path predicate for `.gwc/tasks/<task-id>/g3/**`.
- [ ] Require external current PR head for v1.1 `outcome=pass` CLI validation.
- [ ] Require trusted ancestry verification when current PR head differs from implementation subject.
- [ ] Reject any post-implementation delta path outside the evidence allowlist.
- [ ] Require every declared current-tip CI check to be externally supplied as `pass`.
- [ ] Reject legacy v1.0 for active closure with an explicit migration error.
- [ ] Run/verify GREEN for `tests/test_g3_delivery.py`.

### Task 4: Canonical G3 semantics

**Files:**
- Modify: `skills/gwc-g3/SKILL.md`
- Modify: `projects/gwc/project-instructions.md`
- Modify: `projects/gwc/project-extension.md`
- Modify only if conflicting semantics are present: `core/E2E_DRAFT_PR_DELIVERY_RULE.md`

**Interfaces:**
- Produces one semantic rule: implementation evidence binds implementation subject; current-tip evidence is external and evidence-only delta is enforced.

- [ ] Replace wording that requires the committed delivery record itself to bind exact current PR head.
- [ ] State that evidence-only tip changes recompute tip-level evidence without invalidating unchanged implementation validation/review.
- [ ] State that non-evidence tip drift returns to G2.
- [ ] State explicit v1.0 historical-provenance / v1.1 active-closure migration rule.
- [ ] Preserve independent reviewer and G4 boundaries.

### Task 5: Full validation and Draft PR

**Files:**
- No new production files unless validation reveals a directly related contract test gap.

- [ ] Run current governance unit tests through GitHub Actions.
- [ ] Verify JSON/YAML parsing and schema/template tests.
- [ ] Review full diff against `bad63d466f3d1e40ee5184d75551c3abaa2f0617` for scope drift.
- [ ] Verify changed paths do not include SCRUM-397 delivery artifacts.
- [ ] Create/update Draft PR for SCRUM-615 only after GREEN.
- [ ] Verify exact PR head CI.
- [ ] Leave PR Draft and stop before G4 merge.