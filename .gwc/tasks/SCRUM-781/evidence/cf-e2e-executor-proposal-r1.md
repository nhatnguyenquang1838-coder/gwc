# SCRUM-781 — OPTION B: Persistent E2E Executor proposal (r1)

Status: PROPOSAL_ONLY · no authority granted · no scheduler/repo effect yet.

## 1. Problem statement

Current behaviour is tick-driven: one bounded action per firing, then the turn ends.
Evidence: tick #173 added `resolve_active_plan()` + 3 tests + 1 commit and deferred the
checkpoint transition to #174. Progress is measured by commits/tests, not by accepted
acceptance criteria.

Required behaviour is outcome-driven: one human-approved outcome (G1 R3 Controlled
Failure Campaign) owned continuously until E2E completion or a real hard boundary.

## 2. Architecture

```text
Human-approved G1 R3
        │
        ▼
E2E Executor (single owner, persistent)
  ├─ durable campaign state
  ├─ select next READY work
  ├─ implement/test/fix (RED→FIX→GREEN internal)
  ├─ persist evidence + advance DAG
  └─ stop only on: E2E complete | hard boundary | material conflict
        ▲
        │ health / resume only
10-minute Scheduler (supervisor, no scope authority)
```

Three components:

1. **E2E Executor** — owns the campaign P1→P6. Internal checkpoints (RED, GREEN,
   commit, reload, replay) are not stop points.
2. **Durable campaign state** — survives restarts; the executor resumes from it
   instead of restarting the campaign.
3. **Scheduler supervisor** — 10-minute cadence, health and progress only. It never
   chooses scope, never mints a native firing, never duplicates a Controller request.

## 3. Durable campaign state (proposed schema)

```json
{
  "schema_id": "gwc.q0.campaign-state/v1",
  "run_id": "scrum781-q0-fresh-20261010-r1",
  "plan_ref": "core/node-architect/scrum781-q0-controlled-failure-execution-plan-r3.json",
  "plan_digest": "sha256:...",
  "plan_activation": "PENDING|ACTIVATED|INVALID",
  "head_sha": "…",
  "phase": "P1|P2|P3|P4|P5|P6",
  "work_id": "CF-PRECHECK|CF-RED|CF-FIX|CF-LOAD|CF-REPLAY|CF-CERTIFY",
  "acceptance": [
    {"id": "CF-AC-01", "status": "PENDING|PASS|FAILED", "evidence": ["..."]}
  ],
  "completed_work": ["..."],
  "remaining_work": ["..."],
  "checkpoint_ref": "…checkpoint.sqlite",
  "outbox_ref": "…engineering-exchange.sqlite",
  "continuation_key": "…",
  "status": "RUNNING|WAITING_EXTERNAL|BLOCKED|COMPLETE",
  "stop_reason": null,
  "updated_at": "…"
}
```

Rules:
- The state file is written atomically (write temp + rename) after every verified step.
- `plan_activation` is the only switch that decides R2 vs R3 execution.
- A missing/invalid approved successor plan is `INVALID` → fail closed; it never
  silently falls back to R2.

## 4. Plan activation semantics (fixes P0 from review)

`resolve_active_plan()` must NOT treat `human_approved: true` as activation.

Proposed resolution order:

1. No `approved_successor_g1` → R2 (legacy lane unchanged).
2. `approved_successor_g1` present:
   - `activation_status == ACTIVATED` **and** successor file exists at HEAD **and**
     digest matches the recorded activation receipt → R3.
   - `activation_status` indicates pending → **R2, with an explicit
     `CF_PRECHECK_PENDING` marker** (not silent).
   - `activation_status` claims ACTIVATED but the file/digest is missing/mismatched →
     raise `Q0_PLAN_ACTIVATION_INVALID` (fail closed, no fallback).
3. Activation is written only by the CF-PRECHECK step, after:
   - plan file byte-verified at HEAD,
   - checkpoint transition receipt recorded,
   - frontier re-registered from R3 work items.

## 5. Execution loop (semantic)

```text
load durable state
while status == RUNNING:
    verify authority / scope / source / plan binding
    work = select_next_ready_work()
    if work is None: classify(real blocker) and stop
    result = execute_authorized_work(work)      # may be multi-commit
    if recoverable_failure: repair_in_scope(); continue
    if material_conflict: record + report once; continue independent work
    persist_evidence(); advance_dag()
final_regression(); prepare_draft_pr(); one_e2e_handoff()
```

Native constraint honoured: when the runtime allows only one action per firing, the
executor persists a continuation and uses the **next legitimate firing** — it never
manufactures a firing, counter, or lease.

## 6. Scheduler = supervisor

Per firing:
1. Bind owner/session/counter/worktree (read-only).
2. Read campaign state; if `updated_at` advanced and owner alive → no intervention.
3. If owner stopped with `RUNNING` state → resume from checkpoint on the next
   legitimate firing (no scope change, no new plan).
4. Emit one telemetry record; create a Controller decision request only for a
   material blocker / E2E handoff (ACK #69).
5. Never duplicate a pending GPT request; never re-send the same marker.

## 7. Work packages → acceptance

| Package | Scope | Exit criteria |
|---|---|---|
| P1 | R3 activation + checkpoint migration + CF frontier | CF-PRECHECK 4/4 |
| P2–P3 | Genuine RED, minimal FIX, GREEN, regression, commit | CF-AC-02 |
| P4 | Fresh LOAD_PROOF + same-input REPLAY | CF-AC-03 |
| P5–P6 | Qualification matrix + Draft PR | CF-AC-04 + E2E handoff |

Progress is reported as accepted AC count (e.g. `CF-PRECHECK: 3/4`), not ticks.

Acceptance additions:
- E2E-01 no Controller ACK required between approved phases
- E2E-02 executor advances to next READY work automatically
- E2E-03 RED→FIX→GREEN completes in one development continuation
- E2E-04 recovery continues from durable checkpoint
- E2E-05 scheduler creates no duplicate execution/GPT request
- E2E-06 handoff only at E2E completion or hard boundary

## 8. Migration steps (each with RED→GREEN)

1. `resolve_active_plan` activation semantics + fail-closed tests (fixes P0).
2. Unify CLI: `inspect()`, `workflow()`, `bind_from_plan()` use the resolver; frontier
   reads the resolved plan.
3. `reconcile_engineering_plan_transition(old,new)` — preserves invocations/work/outbox,
   records plan digests, no head-only shortcut.
4. Campaign state store + `advance()` + atomic writes + resume test.
5. Executor loop entry (`execute_campaign`) wired to native firing continuation.
6. Scheduler supervisor path: health/resume only, telemetry, no scope.

Rollback: state store is additive; activation flag can be reverted to PENDING without
touching the checkpoint; R2 path remains intact until step 2 lands.

## 9. Open questions for Controller

1. What exact artifact proves `ACTIVATED` (route field flip vs activation receipt file)?
2. On resume after a stopped owner, is "next legitimate firing resumes the campaign"
   acceptable, or must the Controller issue a typed continuation first?
3. Is per-firing telemetry-only (no browser ping) acceptable while the campaign runs,
   with a single handoff at E2E completion?
