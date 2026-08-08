# SCRUM-275 Implementation Design

## Architecture

SCRUM-275 adds a thin, fail-closed delivery tool chain under
`tools/node_architect/` plus a runtime workflow. Each tool is **pure** where
possible: it reads governance/CI state, validates guardrails, and emits a
structured verdict or mutates only the authorized branch — it never infers
later-gate authority.

## New surfaces

| Surface | Role |
|---|---|
| `tools/node_architect/create_autonomous_task_branch.py` | Create `auto/<run-id>/<task-id>` from latest verified `pre-prod` SHA; enforce head pattern and forbid force push / main base. |
| `tools/node_architect/assemble_autonomous_preprod_pr.py` | Create or update a **Draft** PR targeting `pre-prod`; render PR body via the SCRUM-271 graph/story renderer; forbid `main` base and base change. |
| `tools/node_architect/validate_autonomous_g3_readiness.py` | Exact-head G3 readiness: bind base/head/PR-number/draft readback/diff digest/CI/review; emit PASS only on exact readback. |
| `tools/node_architect/materialize_autonomous_g4_receipt.py` | Validate the SCRUM-272 standing-policy G4 receipt; materialize a head-and-scope-bound, non-expired receipt. |
| `tools/node_architect/merge_autonomous_preprod_pr.py` | Squash-merge the PR into `pre-prod` only; record canonical merge proof binding approved head + resulting `pre-prod` merge SHA. |
| `.github/workflows/autonomous-preprod-runtime.yml` | Runtime: run exact-head CI, call the tools, enforce guardrails, publish G4/G5 status. |
| `tests/test_autonomous_preprod_delivery.py` | Guardrail + branch/PR/CI/review closure tests. |
| `tests/test_autonomous_preprod_g4_merge.py` | G4 receipt materialization, freshness, merge-proof binding tests. |

## Guardrail enforcement strategy

- **Base allow-list**: a single constant `ALLOWED_BASES = {"pre-prod"}`; any
  other base (notably `main`) fails closed.
- **Head pattern**: `^auto/[A-Za-z0-9_-]+/SCRUM-[0-9]+$`; mismatched head fails closed.
- **Force-push / base-change / branch-deletion**: explicit denials returning a
  structured `FORBIDDEN` verdict; the workflow never invokes a force-push.
- **Exact-head drift**: every tool recomputes the live PR head and compares it
  to the bound `head_sha`; any mismatch invalidates prior review/CI/receipt.

## Reuse, not reinvention

- Reuse `scope_hash_calculation.calculate_gate_scope_identity` for scope identity.
- Reuse the SCRUM-271 graph/story renderer for the managed PR body.
- Reuse the SCRUM-272 standing-policy loader for the G4 receipt validation.
- Existing `diff_readback`, `exact_head_readiness`, `draft_pr_creation`,
  `ci_evidence_capture` nodes are wrapped, not modified.

## Merge proof

`merge_autonomous_preprod_pr.py` writes
`.gwc/tasks/SCRUM-275/g4/merge-proof.yaml` binding `approved_head_sha`,
`pre_prod_merge_sha`, PR number, and the G4 receipt scope prefix.
