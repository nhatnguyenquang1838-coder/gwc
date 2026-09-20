# Q0 Live Qualification Runbook v1.0

## Purpose

Operational runbook for a live GWC runtime qualification lane that tests real runtime behavior and self-repairs discovered runtime defects without confusing source implementation, runtime activation, replay verification, and protected-main integration.

## Entry conditions

Before Q0 executes:

1. resolve exact repository and protected-base SHA;
2. bind exactly one Q0 task/parent and current actor claim;
3. freeze the current `q0_baseline_sha`;
4. create a fresh runtime activation from that exact baseline;
5. load current instructions/runtime modules from the declared source root;
6. compile/regenerate source-bound runtime artifacts;
7. materialize `LOAD_PROOF` before the first live probe.

A long-lived conversation/controller may continue, but runtime activation identity MUST be explicit and independently refreshable.

## Live qualification loop

```text
BOOT_Q0
→ ACTIVATE_BASELINE
→ LOAD_PROOF
→ EXECUTE_LIVE_PROBE
→ EXACT_READBACK
→ TYPED_NEXT
→ repeat until matrix complete
```

If a probe finds `GWC_RUNTIME_DEFECT`, freeze the product/consumer child and enter the defect self-fix loop.

## Runtime defect self-fix loop

```text
REPRODUCE_ORIGINAL_FAILURE
→ RED_REGRESSION
→ CREATE_ISOLATED_DEFECT_BRANCH_FROM_Q0_BASELINE
→ MINIMAL_BOUNDED_FIX
→ FOCUSED_GREEN
→ FIX_IMPLEMENTED
→ FIX_IDENTITY_READBACK
→ RELOAD_OR_RESTART_RUNTIME_ON_FIX
→ INVALIDATE_STALE_RUNTIME_STATE
→ REGENERATE_DEPENDENT_RUNTIME_ARTIFACTS
→ LOAD_PROOF
→ FIX_LOADED
→ REPLAY_ORIGINAL_INCIDENT
→ EXACT_READBACK
→ ADVANCE_BEYOND_PREVIOUS_FAILURE
→ FIX_REPLAY_VERIFIED
→ BROADER_RELEVANT_REGRESSION
→ RUNTIME_FIXED
→ PROMOTE_FIX_SHA_TO_Q0_BASELINE
→ IMMUTABLE_REPLAN_IF_REQUIRED
→ RERUN_AFFECTED_SUBTREE
```

## Status semantics

- `FIX_IMPLEMENTED`: bounded source fix exists and focused GREEN passes.
- `FIX_LOADED`: runtime activation proves it loaded the exact candidate identity.
- `FIX_REPLAY_VERIFIED`: original incident passes on that activation and reaches a legal state beyond the old failure.
- `RUNTIME_FIXED`: broader relevant regression/readback passes and all stale dependent state is regenerated or explicitly proven unaffected.
- `FIX_CERTIFIED`: later final clean certification / declared integration target succeeds.

## LOAD_PROOF

Every runtime activation used for acceptance MUST record at least:

```yaml
candidate_fix_sha: <40-hex>
fix_base_sha: <40-hex>
q0_baseline_sha: <40-hex>
branch: <branch>
worktree: <absolute path or durable checkout identity>
worktree_head: <40-hex>
runtime_activation:
  activation_id: <id>
  process_or_session_id: <id>
  source_root: <exact source root>
  loaded_source_sha: <40-hex>
loaded_surfaces:
  instructions: []
  modules: []
  controller_contract_digest: <sha256>
invalidated: []
regenerated: []
incident:
  fixture_digest: <sha256>
  previous_failure_state: <state>
replay:
  result: PASS|FAIL
  exact_readback: true|false
  first_state_beyond_failure: <state|null>
verification:
  broader_regression: NOT_RUN|PASS|FAIL
  exact_readback: NOT_RUN|PASS|FAIL
  evidence_digest: <sha256|null>
```

A changed Git HEAD is not load proof. Receipt evidence is progressive: `FIX_IMPLEMENTED` MUST NOT fabricate future runtime/replay/verification evidence; later statuses add only evidence actually observed.

## Stale-state invalidation

Invalidate only runtime state derived from changed source/semantics, while preserving immutable historical incident evidence.

Potentially stale surfaces include:

- instruction bundles already loaded into an agent/session;
- imported modules or long-lived runtime processes;
- compiled controller/executor contracts;
- RuntimePlan and NodeAllocation derivatives;
- route decisions;
- gate/effect/authority envelopes bound to changed source identity;
- cursor/checkpoint projections;
- native todo/loop state;
- cached validation evidence.

If the changed source is a material dependency of an immutable RuntimePlan, create a new plan revision; never silently mutate the prior plan.

## Original-incident replay

Replay is not equivalent to rerunning a unit test.

It MUST preserve the semantic preconditions and original failure boundary while using the newly loaded runtime identity. Acceptance requires:

1. the old failure no longer occurs;
2. exact readback matches the contract;
3. execution reaches at least one legal state beyond the previous failure point.

If the old failure persists for the same root cause, continue the same defect branch. If a new independent defect appears after successful advance, accept the current fix first and open a new defect branch from the accepted SHA.

## Final clean certification

When no active defect remains, do not certify from a long-lived worker that accumulated repairs.

Create a fresh clean source/worktree at `q0_baseline_sha`, start a fresh runtime activation, reload instructions/modules, regenerate current source-bound artifacts, and execute the complete Q0 qualification matrix from clean state.

Successful exit:

```text
CAMPAIGN_READY_RUNTIME / L3
certified_q0_sha = q0_baseline_sha
Q0 accepted handoff to the declared consumer
```

## Minimum qualification matrix

Q0 MUST cover, when applicable:

- fresh boot does not inherit stale loop/todo/session/branch/authority;
- default route resolves to the current Universal Runtime contract;
- RuntimePlan is immutable and digest-bound;
- NodeAllocation identity/membership is validated;
- Universal Run actually traverses the intended Node Architect execution seam;
- effect-time authority validates actor/action/gate/scope/target/expiry;
- failed exact readback prevents cursor advancement;
- continuation uses legal typed NEXT and does not deadlock on compatibility-only WAIT vocabulary;
- restart recovery resumes from durable current state rather than stale conversation state;
- self-fix proves load + original-incident replay;
- stale source/plan/evidence fails closed;
- replay/idempotency is deterministic;
- at least one real defect path is exercised end-to-end when a qualifying defect exists.

## Authority boundary

This runbook changes qualification semantics only. It grants no G2/G3/G4/G5/G6 authority. Branch creation, repository mutation, PR delivery, merge, runtime reload with external effect, deployment, production configuration, credentials, migrations, or production data remain governed by their applicable authority contracts.
