# SCRUM-781 — CORRECTION43: engineering coordination is not protected C/E

## Binding / correction

Base: `0c77457cf862042025115d4a93b4ac2296183344`; same run
`scrum781-q0-fresh-20261010-r1`, session `20261014_021304_0dc728`, branch
`fix/SCRUM-781-q0-fresh-20261010-r1`, canonical sole DWA worktree.
Exact correction: #595 comment `6259086931`, communication seq43, GPT→Hermes,
SHA256 `edd90f078abb2fd6674f007e0ca96661383d278dc30cae4c60a83509ac2a0076`.
This binds task intent, not typed C/E or a grant of effect authority. The current
AGENTS Universal-v2 override and immutable R2 plan still govern source effects.

The prior wrapper unconditionally used frozen protected activities. A qualified
M1 would only have moved the blockade to typed continuation M2, legacy G2 M5 or
native settlement/mailbox M7. Native102 proved communication/wiring, not Q0 work.
This correction supersedes a background observer as an engineering prerequisite;
qualified typed observation is still required for the protected workflow itself.

## Explicit routing and identity

TaskContext `workflow.mode` accepts exactly:

- `Q0_ENGINEERING_COORDINATION`: `generic-engineering-m1-m7/v1`, evidence
  `ENGINEERING_COORDINATION_NOT_PROTECTED_CE`.
- `PROTECTED_TYPED_CE`: existing protected activities, evidence
  `PROTECTED_TYPED_CE`. No frozen SCRUM-841 activity/manifest/profile is changed.

The Q0 CLI selects engineering mode explicitly by its versioned route policy
`core/node-architect/q0-engineering-coordination-route-r1.json`. The generic graph
contains no Jira ID, issue number, branch-prefix or task-specific condition.
The policy is source-bound and the existing immutable RuntimePlan is unmodified.

## Engineering M1–M7 contract

| Activity | Actual implementation |
|---|---|
| M1 | Host performs one logical paginated human #595 read; typed bodies stay opaque. Filter run/protocol/author before emitting/persisting; validate latest command identity/seq/source/reply. No observer daemon or typed admission claim. |
| M2 | Validate TaskContext, current source/plan/owner through a fresh callback and exact task intent digest. New unprocessed intent requires reconciliation, not automatic execution. |
| M3 | Select priority work from source-bound policy. Completed identical input fingerprints are not rerun for coverage/progress. |
| M4 | Scope concrete dependency/conflict to selected work; return an explicit later-stage WAIT without a global protected C/E HOLD. |
| M5 | Durable work claim before a fresh owner/source/action revalidation and an allowlisted host subprocess. This initial executor supports read-only validation only; stronger effects need their own governing path. |
| M6 | Read the actual result artifact, verify content/output digests, exact source HEAD, exit code, expected result and non-live reconstructed classification. A report string is not execution proof. |
| M7 | Reserve a HOST_COORDINATION report/exchange request in durable outbox; current Hermes agent executes Desktop tools through the installed exchange skill. WAIT for host delivery is not protected M7 PASS or native settlement. |

The first prioritized work is the existing reconstructed DWO Login native probe:
`python -m scripts.scrum781_q0_login_fixture --engine native`.
It exercises a real source-bound GWC epoch-routing probe and deterministic login
requirements cases. It is **not** live DWO authentication, original incident
replay, a native gate receipt, LOAD_PROOF or L3. Missing original evidence is not
fabricated; no production/auth/secret operation is admitted.

## Durability and continuation

The same physical SQLite checkpoint gains separate `engineering_*` tables. Old
protected workflow/invocation rows remain unchanged. Invocations and work have
independent atomic unique claims. An interrupted/unknown action is not retried
blindly; another owner/tick cannot clear it. Human consumption is persisted only
after context validation/processing, with a new-consumption flag distinct from
repeat reads. It is LOCAL_ONLY and never a canonical typed cursor.

Source drift fails closed. An explicit HEAD-only additive reconciliation checks
real Git ancestry/worktree/branch, archives prior engineering state and exact-reads
the updated digest. A changed plan/input/task context is not silently adopted.
Pending exchange context is retained separately so an old request is not rebound
to a new HEAD. A no-new-work tick retains pending request references without
reexecuting completed work or emitting a new request merely to wake GPT.

## RED / GREEN / impact

Observed initial RED: 5 engineering assertions failed and protected negative
passed. The two task bindings were both wrongly forced into protected M1 HOLD.
The host-parser missing-module RED was also observed, followed by a concrete
historical-source-coupling RED and repair (validate the selected current command,
not obsolete source references as authority).

Focused affected-consumer tests: **56 PASS + 5 subtests PASS** after the route,
host, prompt-routing and genuine-firing admission corrections.
Coverage includes two bindings, strict protected mode, duplicate invocation/work,
unknown/crashed effect no-repeat, real scratch-Git additive reconciliation,
prohibited-effect rejection even if listed in a candidate scope, and human/typed
separation. These are synthetic/unit acceptance fixtures, never native firings.
No unchanged wide suite is claimed. UA index remains at
`3b6c22be933036887a7ae96002e5a48677583812`, without nodes for new targets: graph
coverage UNKNOWN, not low impact. Task-me packageRoot is null; no DAG execution
is claimed. Actual consumers are the task runner, Q0 CLI and focused tests.

## Host acceptance boundary

The installed native Loop prompt must delegate its one-shot read to engineering
M1 (not perform a second collection read outside the graph), invoke the routed
CLI, and fulfill its returned report/exchange request through the existing host
skills/outbox. This is prompt-only, not a scheduler reset or core/plugin change.

Source/test success alone does NOT satisfy the requested genuine-firing
acceptance. Report the actual fresh native key, owner, selected action/result,
artifact digest and stage reached when available; otherwise report native proof
PENDING and resume only on the next genuine owner firing. No synthetic tick,
manual settlement or counter reset is permitted to make this acceptance pass.

Parent: `UR.G2 / RUN_NOT_COMPLETE`. Protected C/E remains independently gated.
