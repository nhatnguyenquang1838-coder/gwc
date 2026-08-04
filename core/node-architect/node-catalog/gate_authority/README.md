# Gate Authority Node Family

```text
Task: REVAMP-GWC-017
Batch: batch-02-gate-authority
Family: gate_authority
Planned nodes: 9
Authority boundary: G1_ALIGNMENT_G2_EXECUTION
```

## Purpose

This family models the gate authority layer used by GWC agents before any repository-changing action.

It keeps approval, scope, evidence, and boundary decisions explicit so agents can continue safe preparation work but stop at exact human approval boundaries.

## Nodes

| Node | Type | Purpose |
|---|---|---|
| `gate_authority.gate-state-resolution` | gate | Resolve current gate from artifacts and task state. |
| `gate_authority.approval-token-generation` | workflow | Generate exact approval commands. |
| `gate_authority.approval-command-validation` | gate | Validate exact approval commands. |
| `gate_authority.scope-hash-calculation` | tool | Calculate deterministic scope hash inputs. |
| `gate_authority.authority-boundary-check` | gate | Block authority crossing without the right gate. |
| `gate_authority.evidence-artifact-map` | schema | Map gate evidence to canonical artifacts. |
| `gate_authority.gate-transition-decision` | state | Decide pass/block/continue/fail-closed. |
| `gate_authority.g2-execution-envelope-render` | workflow | Render bounded G2 execution envelopes. |
| `gate_authority.blocked-action-escalation` | workflow | Generate the next required approval/remediation command. |

## Guardrails

```text
✅ exactly 9 nodes
✅ all nodes use authority_boundary=g2_required
✅ all nodes are limited to G1_ALIGNMENT and/or G2_EXECUTION
✅ no merge/deploy/production authority
✅ no runtime engine implementation
✅ no all-81 catalog implementation
```

## Admission criteria

This batch is valid only after:

```text
batch-01-intake-context merged to main
exact post-merge CI for batch-01 is available or latest main is verified
runtime node schema validation passes
family validator passes
governance unit tests pass
```

## Explicit exclusions

```text
merge
auto_merge
deploy_release
production_config_data
secrets_credentials
migration
runtime_engine
scheduler_worker
all_81_node_catalog
```

## G4 merge authority note

This family resolves and validates G4 approval *envelopes and tokens* (scope hash, expiry, head binding) only. It does **not** perform the merge and must not emit `merge`/`auto_merge` connector calls. The actual G4 merge execution is a separate human-triggered action governed by `core/GATE_LIFECYCLE_CONTRACT_v1.0.md` (G4_MERGE section).

When a valid `APPROVE G4_MERGE <approval_id> <scope_hash_16> <expires_at_utc>` token is verified, the merge MUST be executed through the repository `g4-g5-evidence.yml` workflow chain, not a bare `gh pr merge`:

1. Post the verified token as a **PR comment** so the `g4-authority` job publishes the `<!-- gwc:g4-authority-receipt ... -->` receipt.
2. Confirm the receipt comment exists and its marker fields match the token.
3. Merge via the GitHub UI or `gh api` merge endpoint so `pull_request.closed` fires `g4-merge-proof` (`<!-- gwc:g4-merge-proof ... -->`).
4. Poll `g5-status` for `classification: success`.

A direct `gh pr merge` bypasses this chain: the merge succeeds and CI passes, but the `g4-authority-receipt` is never created, so `g4-merge-proof` and `g5-status` fail, and `g5-recovery` cannot backfill it (the merge-commit message lacks the original G4 `approval_id`/`head_sha` provenance). Do not fabricate receipts.
