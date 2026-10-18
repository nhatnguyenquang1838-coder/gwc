# SCRUM-781 — Task-aware M1–M7 wiring, bounded implementation R1

## Binding / scope

Same run `scrum781-q0-fresh-20261010-r1`, session `20261014_021304_0dc728`,
branch `fix/SCRUM-781-q0-fresh-20261010-r1`. This implements the attached
Controller design direction, not native C/E admission or parent Q0 acceptance.
No Hermes core, frozen SCRUM-841 manifest/profile, topology, mailbox records,
issuer, lease, scheduler state, production or protected branch is modified.

## Implemented

1. `task_context_binding.py`: generic TaskContext validation; committed RuntimePlan
   byte readback, objective/AC, dependencies/scope/authority references, exact
   repository/branch/HEAD/worktree, GPT URL, session and skill capability binding.
   Actual task source is the committed RuntimePlan, **not a claimed live Jira fetch**.
2. `task_m1_m7_runner.py`: generic LangGraph entrypoint reusing the existing
   M1–M7 activity functions. No task-ID special case in the new engine. M1–M7
   topology/host settlement semantics retained. Qualified typed observation may
   only come through host-injected read+verify capabilities. Missing provider
   yields real `HOLD / OBSERVER_UNQUALIFIED`.
3. `controller_exchange_adapter.py`: closed-schema typed host requests, durable
   SQLite pending ledger, atomic reserve-before-send, immutable terminal receipt,
   exact task/run/URL/marker checks, separate read-only response-resume path.
   `BROWSER_EXCHANGE_VERIFIED` never becomes typed C/E admission or authority.
4. Q0 CLI `workflow` and compatibility `inspect --tick` invoke the generic runner
   after actual owner/session/tick preflight; checkpoint survives subsequent
   firings on the same source identity. `prepare` and no-tick `inspect` stay
   read-only. A tick-scoped inspect now writes a scratch workflow checkpoint;
   this is an explicit behavior change, not a read-only claim.
5. Source-owned prompt prioritizes invocation and host-admission repairs instead
   of unrelated coverage work. Existing installed prompt is NOT silently rewritten;
   its existing `inspect --tick` command routes through the new CLI wiring.

## Independent coordination vs graph M7

An explicit user Controller-contact request can produce `HOST_COORDINATION`
outside the graph dependency chain while M1 holds. It does NOT mean M7 was reached.
A request emitted by the M7 activity is separately labeled `M7`. Browser I/O stays
in the trusted Hermes skill capability, never in a graph node. Frozen M7 mailbox
and settlement logic is preserved.

## Acceptance / limitations (not hidden)

- Generic binding + real LangGraph invocation tested for TASK-A and TASK-B
  fixtures. These are two **unit bindings**, not two live task admissions.
- Focused test results and actual source-bound Q0 probe are reported separately.
- Host skill send/read functions are injectable capability interfaces. Installed
  skill guidance was loaded by DWA; autonomous CLI-to-desktop tool dispatch is
  **not yet a qualified host service**. Empty capability registry holds M1.
- Canonical typed observer read/verify producer is still unavailable; this repair
  does not create one or certify a homemade receipt.
- Native firing acceptance is pending while scheduler is paused. No simulated
  tick, manual fire/settle or false tick-100 evidence is created.
- M2–M7 and verified response-to-graph end-to-end remain unproven. No L3,
  LOAD_PROOF, authentic original incident replay, or Q0 closure claim.
- Existing 16 legacy failures remain outside this bounded repair; no unchanged
  full-suite rerun is presented as progress.

## Impact evidence / corrected historical claims

UA metadata is at commit `3b6c22be933036887a7ae96002e5a48677583812`
(last analyzed 2026-08-24); the target workflow files are not modeled. Graph
coverage is insufficient, not low impact. Task-me host config has no packageRoot;
no Task-me DAG execution is claimed. Exact-source caller scans identify the Q0
CLI, Q0 integration wrapper and existing M1–M7 activity/harness tests as consumers.
The frozen activity library is reused, not rewritten. Six foreign workflow files
are preserved and hash-compared against the pre-integration manifest.

Historical tick-95/96 assertions of “zero coverage” based only on literal grep
were insufficient: functions can be exercised transitively, and the existing
qualification coverage audit already records related unit/persistence coverage.
Those assertions must not be used as evidence that native qualification advanced.

## Controller review request

Review the exact pushed candidate as a **bounded wiring/coordination foundation**,
not completed AC-01..AC-10 or end-to-end PASS. Request disposition on:
1. Generic wrapper reusing frozen activities vs altering the frozen definition.
2. Independent explicitly authorized HOST_COORDINATION while M1 holds.
3. Canonical host provider source and qualification path for real typed observer,
   continuation bindings and desktop skill dispatch.
4. Native firing acceptance after a real owner firing (not a synthetic test).

Parent remains `UR.G2 / M1_HOLD / RUN_NOT_COMPLETE`.
