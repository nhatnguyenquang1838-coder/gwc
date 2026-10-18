# SCRUM-781 — Hermes Skill Capability Bridge R1 correction

## Binding and authority

Base: `3926191c93f475aa0c35c3efddce056e3a155f8a`.
Run: `scrum781-q0-fresh-20261010-r1`; session: `20261014_021304_0dc728`.
Branch: `fix/SCRUM-781-q0-fresh-20261010-r1`.
Source authority: the live `AGENTS.md` UNIVERSAL_V2_DEVELOPMENT override and
source-bound Q0 execution plan; bounded correction scope supplied in Controller
Independent Review R1. No frozen activity/manifest/profile, Hermes core/plugin,
typed mailbox/continuation, issuer/lease or native scheduler changes.

## CR-01/04 — Actual host capability boundary

`hermes_skill_capability_bridge.py` resolves the installed `dwa-gpt-exchange`
skill, verifies its frontmatter identity, hashes its actual bytes, binds the
current session and exact preview URL, and exposes:

- `controller_exchange.send_read_verify`
- `controller_exchange.read`

The bridge returns **HOST_ACTION_REQUIRED** tool actions, consumed by the current
Hermes agent via the existing `desktop_preview`/`drive_preview` tools. This is
not an autonomous subprocess GUI service: installed Hermes
`tools/preview_tool.py` explicitly describes preview read as an agent callback.
A tool-action request is never persisted as a successful exchange receipt.
Missing live preview binding returns `HOST_PREVIEW_CALLBACK_REQUIRED`, without
registering browser send capabilities or a typed observer. Q0 CLI now invokes
the resolver instead of passing a hardcoded empty dictionary; host-injected
capabilities are supported. `typed_observer.read_verified` and
`typed_observer.verify` remain unregistered; M1 stays HOLD.

The actual installed skill resolved on this host:
`$HERMES_HOME/skills/dw-superapps/dwa-gpt-exchange/SKILL.md`.
SHA256: `f75f0a2b38678470415581c7ff6a176201bfcb27d4befb13ece1e88066295266`.
That hash is host binding evidence, not portable admission authority.

A real completed GPT response was read from the exact bound conversation:
`https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6ad380a6-c280-83ec-bb3f-75cef495e848`.
Marker: `DWA-REVIEW-05829f757569f4f1` in the user turn immediately before
`SCRUM-781 — Independent Review R1`, verdict
`CHANGES_REQUESTED / LEVEL_1_ACCEPTED / HOST_ADAPTER_BLOCKED`.
The same page exposed `Response complete`. The bridge verified this correlation
and moved the existing durable outbox from `MESSAGE_SENT_VERIFIED` to
`CONTROLLER_RESPONSE_VERIFIED`; independent SQLite readback confirmed it.
This is **read/resume through the new bridge**, not a claim that the original
send used it. A fresh send through the new bridge is a separate host acceptance
step; its live request and receipts stay in host scratch, not this immutable
source report. No full transcript is committed here.

## CR-02 — Delivery integrity and concurrency

Explicit transition policy rejects a weaker receipt after verified delivery.
Blocked recovery requires an exact prior-receipt/request/URL/session/marker-bound
reconciliation. Terminal responses are immutable. `BEGIN IMMEDIATE` plus
compare-and-set of status and prior receipt protects transitions. Reader callbacks
carry their pre-read snapshot through CAS; exception handling cannot downgrade a
concurrently delivered request. History rows preserve old/new transition evidence.
Stage and Send each have a unique durable action claim before UI execution;
a crash/ambiguous attempt cannot cause automatic retyping or reclicking.

Three original defect assertions were observed RED, then GREEN: delivery
regression, stale writer and blocked recovery. The actual concurrent two-writer
test allows one winner and rejects the other with `OUTBOX_CAS_CONFLICT`.

## CR-03 — Explicit source-head reconciliation

`reconcile_source_head(old_context,new_context,repository_root=...,reason=...)`
accepts only a HEAD-only context change, checks actual worktree/branch/current
HEAD plus real additive Git ancestry, requires the exact prior checkpoint digest
and effect-free `M1 HOLD / OBSERVER_UNQUALIFIED`, archives the old checkpoint row,
and updates bindings under atomic CAS with durable readback. It never changes
an old invocation result, scheduler state, browser URL, session or RuntimePlan.
Q0 CLI selects the existing run checkpoint across source HEAD changes; ambiguity
fails closed. Without an explicit reconciliation, context drift still blocks.
The positive test uses a real scratch Git repository and additive commits, not a
mock ancestry flag. This is not a generic authority rebind or migration tool.

## CR-05 — Native firing supplement

See `native100-workflow-supplement-r1.json`. It supplements the original host
record, rereads the actual invocation row, and explicitly distinguishes the old
browser-blocked snapshot from the later delivered review. It does not rerun tick
100, manufacture a firing, or settle a tick. Native state read during repair was
`active / ticks_fired=100 / awaiting_response=false`.

## Verification and limits

Focused correction and affected-consumer tests: **43 PASS + 5 subtests PASS**.
No unchanged wide-suite run. Existing 16 classified legacy failures are not
repaired or promoted to GREEN by this focused result. `git diff --check` PASS.
UA metadata remains stale at `3b6c22be933036887a7ae96002e5a48677583812` and has
no nodes for these targets; impact coverage is UNKNOWN, not low impact.
Task-me host config and exact source/import scans were checked; no Task-me DAG
execution is claimed. Actual consumers include the Q0 CLI, generic runner,
exchange tests and workflow-entrypoint tests. Six foreign workflow files are
outside this correction and must retain their manifest hashes.

**Actual activity reached:** existing native100 M1 HOLD; M2–M7 NOT_REACHED.
**Native owner:** Hermes native Loop; DWA performs no reset/fire/settle.
**Open:** canonical qualified typed observer; native C/E admission;
response-to-graph/M7 end-to-end acceptance. Browser exchange evidence never
becomes typed C/E, M7 PASS, LOAD_PROOF, original-incident replay or Q0 L3.
**Parent:** `UR.G2 / M1_HOLD / RUN_NOT_COMPLETE`.
