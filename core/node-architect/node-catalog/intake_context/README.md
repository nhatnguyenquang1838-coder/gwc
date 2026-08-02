# Intake Context Node Family v0.1

```text
Task: REVAMP-GWC-016
Batch: batch-01-intake-context
Family: intake_context
Authority boundary: G0_CONTEXT
Planned nodes: 9
Runtime behavior change: none

SCRUM-176 Update (2026-07-31)
- Source resolution extended with typed contract (intent, outcome, constraints, exclusions, entry_guards, reason_codes)
- Exact-head CI evidence: main@3a0bee57058672e4167bac0ea5ff02b3ac9080d9
- Validator: tools/node_architect/validate_node_catalog_intake_context.py
- Tests: tests/test_node_catalog_intake_context.py (16 tests PASS)
```

## Purpose

This family adds the first controlled node catalog batch after the controlled 81-node expansion plan.

The nodes are **read-only G0 context nodes**. They structure request intake, source resolution, repository identity, protected base capture, risk classification, read/write scope rendering, intake-card rendering, and context-gap escalation.

## Source Resolution Typed Contract

The `intake_context.source-resolution` node extends the basic descriptor with typed fields:

| Field | Type | Purpose |
|---|---|---|
| `intent` | string | Describes the purpose of source resolution |
| `outcome` | string | Describes the expected typed result |
| `constraints` | string[] | Bounded rules for deterministic resolution |
| `exclusions` | string[] | Bounded exclusions (no runtime behavior, deployment, migration, credentials) |
| `entry_guards` | string[] | Required gates and authority boundaries |
| `reason_codes` | string\|object | Stable machine-readable codes (ACCEPTED, AMBIGUOUS, MALFORMED, MISSING_EVIDENCE, INVALID_MODE) |

**Deterministic resolution:** Source mode must be resolved as `REPO`, `PACKAGE`, or `MIXED` deterministically.

**Fail closed:** When source authority cannot be distinguished, reject with a stable reason code.

**Provenance:** Evidence must be verified, not guessed.

## Risk Classification Typed Contract

The `intake_context.risk-classification` node emits a closed `risk_profile` object before gate routing:

| Field | Type | Purpose |
|---|---|---|
| `risk_level` | string | Repo risk class, expressed as `R0`, `R1`, `R2`, or `R3` |
| `risk_flags` | string[] | Canonical escalation flags such as source stale, scope ambiguous, or production-triggered risk |
| `required_gate` | string | Minimum next gate required by the classification |
| `approval_requirements` | string[] | Human-readable control requirements that must be satisfied before advancing |
| `reason_codes` | string[] | Closed vocabulary of supported risk reason codes |
| `source_bindings` | object | Exact intake, source, repository, and protected-base evidence bindings |
| `classified_at` | string | ISO-8601 timestamp for the classification event |

Supported `reason_codes` are closed to:

- `RISK_PRODUCTION_OPERATION`
- `RISK_SECRET_CHANGE`
- `RISK_DESTRUCTIVE_OPERATION`
- `RISK_MIGRATION`
- `RISK_RELEASE_DEPLOYMENT`
- `RISK_SCOPE_AMBIGUOUS`
- `RISK_SOURCE_STALE`
- `RISK_UNCLASSIFIED`

**Deterministic classification:** equivalent intake facts must produce the same `risk_profile`.

**Fail closed:** missing, stale, ambiguous, or conflicting evidence must not classify as low risk.

**Evidence binding:** the output must stay bound to request intake, source resolution, repository identity, and protected-base capture.

## Read / Write Scope Typed Contracts

The scope nodes are the two batch-1 renderers that turn intake evidence into bounded file sets for later envelope assembly.

| Field | Read scope | Write scope |
|---|---|---|
| `intent` | Build the bounded read set from governance and task inputs. | Build the bounded write set and explicit exclusions for later G2. |
| `outcome` | Deterministic `files_read` evidence with bounded provenance. | Deterministic `files_write` evidence with blocked actions. |
| `constraints` | Verified inputs only, read-only, fail closed, repo-bounded. | Repo-relative paths only, fail closed, exclude protected actions. |
| `exclusions` | Runtime behavior, deployment, migration, credentials, write paths. | Direct push, force push, branch deletion, merge, deploy, release, production config, credentials, secrets, migration, production data. |
| `entry_guards` | `G0_CONTEXT`, `read_only` | `G0_CONTEXT`, `read_only` |
| `reason_codes` | `ACCEPTED`, `MISSING_EVIDENCE`, `MALFORMED_INPUT`, `SCOPE_DRIFT` | `ACCEPTED`, `EMPTY_SCOPE`, `PROHIBITED_ACTION`, `MALFORMED_INPUT`, `SCOPE_DRIFT` |

## Intake Card Runtime Contract

`intake_context.intake-card-render` remains a thin static `G0_CONTEXT` / `read_only` descriptor. Its runtime contract is explicitly mapped to:

| Surface | Path |
|---|---|
| Closed schema | `schemas/intake-card.schema.json` |
| Pure evaluator | `tools/node_architect/intake_card_render.py` |
| Entrypoint | `render_intake_card` |
| Focused regression | `tests/test_intake_context_intake_card_render_m4.py` |

The family validator checks that the schema and evaluator exist, the schema is valid Draft 2020-12 JSON Schema, `artifact_type` is exactly `intake-card`, and the evaluator exports the expected callable.

The renderer:

- validates required fields, artifact type/version, and task/repository/base bindings across all upstream artifacts;
- recomputes the SCRUM-179 `decision_digest` and SCRUM-180/181 `scope_hash` values from canonical semantic payloads;
- binds `scope_hash` to source mode/revisions, risk digest, read-scope hash, and write-scope hash;
- hashes the complete redacted card except `created_at` and `snapshot_hash`, including status and reason codes;
- redacts protected keys regardless of value type and validates the closed explicit-directive vocabulary;
- emits a schema-valid blocked card on ordinary contract, binding, hash, or redaction failures;
- keeps every authority field fixed to `false`.

## Guardrails

```text
✅ exactly 9 nodes
✅ all nodes belong to intake_context
✅ all nodes are limited to G0_CONTEXT
✅ no production runtime behavior
✅ no scheduler / worker / storage adapter
✅ no G2/G3/G4/G5/G6 authority
```

## Nodes

| Node | Purpose |
|---|---|
| `intake_context.request-intake` | Normalize the user request into a typed intake contract with intent, outcome, constraints, exclusions, entry_guards, and reason_codes while preserving G0_CONTEXT gate and read_only authority. |
| `intake_context.source-resolution` | Resolve REPO / PACKAGE / MIXED source instruction. |
| `intake_context.repo-identity-check` | Verify repository identity, default branch, protected branch, and execution mode assumptions. |
| `intake_context.protected-base-capture` | Capture exact protected-base SHA and typed readback/drift evidence for later validation. |
| `intake_context.risk-classification` | Classify risk flags before gate routing. |
| `intake_context.files-read-scope` | Render the required read set and provenance for the current task. |
| `intake_context.files-write-scope` | Render bounded write paths, exclusions, and later G2 guardrails. |
| `intake_context.intake-card-render` | Produce the standard GWC intake card. |
| `intake_context.context-gap-escalation` | Fail closed when required context or evidence is missing. |

## Validation

Run:

```bash
python -m unittest tests.test_intake_context_intake_card_render_m4 -v
python -m unittest tests.test_node_catalog_intake_context -v
python tools/node_architect/validate_node_catalog_intake_context.py
```

## Compatibility

This batch extends the runtime kernel and the controlled catalog plan. It does not replace existing reference nodes, checkpoint contracts, simulation rules, or package export rules.

The SCRUM-182 renderer validates upstream artifact contracts but does not implement or repair the separate SCRUM-179, SCRUM-180, or SCRUM-181 evaluators.

## Impact

```text
✅ retains 9 catalog node definitions
✅ adds closed intake-card runtime schema/evaluator linkage
✅ adds deterministic digest, binding, redaction, and drift validation
✅ adds focused and family regression coverage
❌ does not implement all 81 nodes
❌ does not grant execution, merge, deploy, release, or production authority
```
