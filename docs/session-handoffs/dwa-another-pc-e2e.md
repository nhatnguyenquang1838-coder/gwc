# DWA — E2E handoff to another PC

## What is ready vs not ready

This repository handoff is portable bootstrap material, not proof that the destination PC is configured. Source commit before this document: `6f94e1baba936938085fedf05035ca942da30492`. Read `docs/session-handoffs/dwa-loop-recovery-641.md` fully: it contains the correction of unverified REPORT #328. Do not replay that report as truth.

Bound run: `scrum781-q0-fresh-20261010-r1`. Repository: `nhatnguyenquang1838-coder/gwc`. Branch: `fix/SCRUM-781-q0-fresh-20261010-r1`. Workspace repository: `nhatnguyenquang1838-coder/DW-SuperApps`. Product/source mutation belongs only in the registered child linked worktree, not its submodule anchor.

The destination has a NEW Hermes conversation/session ID and NEW local OS/process identities. Record those honestly and reference old conversation `20261014_021304_0dc728` as provenance; do not impersonate its session/process/lease. Canonical run and branch remain unchanged. Parent workspace gitlink must not be bumped.

## 1. Source-PC freeze and ownership transfer

This handoff session performs only documentation/commit/push; it yields Q0 engineering work after delivery. It does NOT automatically stop a possibly active old Loop. Before destination becomes writer:

1. On the old session, read `/loop status` in the live Desktop. Use `/loop pause` through that SAME session if active. Read `/loop status` again and retain confirmation. No counter reset or SQLite edits.
2. Verify no admitted worker/Executor remains active in the old worktree. A Git-clean tree alone does not prove no writer. Do not kill unrelated processes.
3. Record old Loop pause/writer-release and new session/PC ownership in the handoff projection. If the source cannot be reached, stay read-only and ask for the owner-release decision; do not silently start concurrent execution.
4. Native/controller-specific host/lease admission, if actually active, must be revalidated separately; a Git push or this prose is not an execution lease.

Old runtime discrepancy: CLI `LoopManager` returned None while the previous assistant reported UI active at tick 641. Do not copy state.db or infer stopped status. Reconcile the actual Desktop backend/profile store.

## 2. Destination preflight and Git bootstrap

Use the destination PC's real paths and shell; do not copy Mac absolute paths. Do not sync secrets, browser cookies, auth stores, state.db, locks, leases, PIDs or scheduler rows. Use existing destination-local authentication. Missing authentication is a user-operated login boundary.

1. Open/locate the DW-SuperApps workspace. Read current `AGENTS.md`, `workspace.yaml`, `docs/runbooks/ISOLATED_SUBMODULE_WORKTREE.md`, and `docs/skills/dw-git-worktree/SKILL.md`.
2. Resolve the registered GWC child anchor from `workspace.yaml` and `.gitmodules`. Do not assume the child anchor is a writable development surface. If absent, initialize only the registered submodule through supported workspace policy. Do not make a standalone writable clone elsewhere or change the parent gitlink.
3. Verify repository origin is exactly `nhatnguyenquang1838-coder/gwc`; inspect existing child worktrees and branches. Fetch the remote Q0 branch. Check exact remote SHA and require it to contain both handoff documents. Fetch default main for read-only source verification, without switching the Q0 branch to main.

Commands below are templates for the AGENT to resolve, not user-ready commands with invented paths. Set `ANCHOR` to the verified registered child anchor and `WT` to the workspace-relative canonical destination `worktrees/gwc/SCRUM-781-q0-fresh-20261010-r1`; use platform-appropriate quoting.

```sh
git -C "$ANCHOR" fetch origin fix/SCRUM-781-q0-fresh-20261010-r1
git -C "$ANCHOR" worktree list --porcelain
git -C "$ANCHOR" branch --list fix/SCRUM-781-q0-fresh-20261010-r1
```

If neither a local branch nor that worktree exists, create the LOCAL branch from its exact remote tracking branch, then create the linked worktree:

```sh
git -C "$ANCHOR" branch --track fix/SCRUM-781-q0-fresh-20261010-r1 origin/fix/SCRUM-781-q0-fresh-20261010-r1
git -C "$ANCHOR" worktree add "$WT" fix/SCRUM-781-q0-fresh-20261010-r1
```

If the branch exists, reuse it only in its owning worktree. If clean and strictly behind the remote, fast-forward with `git merge --ff-only origin/fix/SCRUM-781-q0-fresh-20261010-r1` inside that worktree. Dirty, diverged, occupied or unexpected paths => stop and preserve; no reset/rebase/force/delete. Do not create duplicate branch names or a second writer to evade occupancy.

Verify destination worktree root, branch, clean status, exact HEAD==remote head, upstream, and both committed handoff files. Handoff commits change engineering HEAD from `48f71158`; do not describe them as refreshed native qualification. COMMAND #327 is exact-bound to `48f71158`: isolated evidence execution on that immutable source may be possible, but new-HEAD qualification requires current applicable contract/rebinding, not silent SHA substitution.

## 3. Recreate the session task list (projections, not canonical runtime records)

Create these tasks through the destination's supported task/todo UI/tool; inspect its schema first. Do not fabricate Jira work items or claims.

- T1 SOURCE_OWNER_RELEASE: confirm old Loop paused and sole-writer handover. Blocking for writes/scheduling.
- T2 LOCAL_BOOTSTRAP: repository/registration/linked worktree/branch/remote readback; exact source instructions loaded.
- T3 PREVIEW_BIND: in-app exact URL/auth/liveness/composer/readback qualification.
- T4 ACK_CORRECTION: send one verified ACK/correction for REPORT #328; no duplicate.
- T5 W5_REDO: genuine scratch-only B0→B5 under complete #327 and applicable exact-source binding; no invented matrix/load/stale-state claims.
- T6 CONTROLLER_HANDOFF: exact evidence report/readback, no W6/native materialization without authority.
- T7 LOOP_START: only after T1-T3 and binding/scope preflight; create one destination-local Loop and verify its real state.

T1/T2/T3 are the initial dependency frontier; ACK requires T3. Independent safe read-only investigation can proceed without waiting for effect authority. Browser failure blocks notification, not unrelated authorized scratch work.

Keep M1 same-run/communication; M2 source/worktree/HEAD; M3 writer/delegation; M4 executed work; M5 qualification frontier; M6 verification/report; M7 browser notification. Observations only, no fabricated receipts.

## 4. Bind authenticated Hermes in-app preview

Exact authorized destination:

https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6adec292-a4a0-83ec-a9de-1d9b36f2297c

Load `dwa-gpt-exchange` + `hermes-session-handoff`. Discover live `desktop_preview`/`drive_preview` schemas. Open the exact URL. Require `desktop_preview(read)` URL equality plus fresh `drive_preview(elements)` composer and authenticated content. Navigation success alone is insufficient. If login wall: stop with GPT_LOGIN_REQUIRED and let user sign in IN APP; never type or request credentials. If bridge unresponsive: IN_APP_BROWSER_UNAVAILABLE; do not fall back to browser_exec/external Chrome/raw HTTP/clipboard or alternate URL. Do not upgrade/restart core without separate consent.

Read the latest page. If GPT busy or the same correction already present, do not send. Otherwise type one concise correction using fresh composer ref, verify its value, submit once and exact-read a NEW user turn carrying marker `DWA-PC-HANDOFF-328-CORRECTION-R1`. Preserve same URL, new-session identity, marker and truthful delivery result locally. Marker appearing in a draft is not delivery.

ACK content: continuing the same run/branch on another PC after source-owner release; REPORT #328 is unverified, withdrawing its unsupported LOAD_PROOF, assigned PASS matrix, changed-file=>stale inference and contradictory B5 NOT_RUN claims; W5 remains incomplete pending exact #327 scratch-only redo; no L3/native acceptance/W6 claim. Ask Controller to reconcile current exact engineering HEAD/evidence source if needed. Do not claim new authority.

## 5. W5 source/evidence recovery

Read full COMMAND #327 at https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6434766274 through the admitted communication path. A timer itself grants no mailbox poll/consume rights. Read #326 and #328/corrections as evidence, not typed C/E grants. No blind sequence allocation from historical seq328.

Use exact source definitions and observed signatures. Source scratch from immutable approved commit where necessary; preserve canonical worktree/native state. Do not write source merely to repair a harness. On destination discover Python/environment/dependencies; scratch venv from old Mac is not portable. No hidden package install or provider/network dependency.

Redo B0→B5 with real outputs: B0 exact local/remote/PR/source bindings; B1 canonical digests/topology/both allocations and derivative producer where applicable; B2 fresh Python 3.11 process actually imports modules and executes native route/profile with byte comparisons and measured instruction/process/source identities; B3 evidence per matrix entry and all six specified regression files; B4 consumer-bound changed-file semantics, not count-based stale labels; B5 only under its prerequisites, with authentic replay/forward-progress fields and exact current timestamp. Test outcomes, field names and digests must come from tools. No fake PASS list, future timestamp, guessed state string, or suppressed stale dependency. REPORT #328's certifier calls failed BEFORE stale checks, so stale rejection remains unproven.

W4 acceptance for W5 entry is in #327; it does not physically stamp the native matrix. Avoid the opposite error of requiring W6 to prove structural DAG completion: #327 explicitly permits structural PASS candidate before W6. Distinguish scratch proposal/evidence from native state mutation.

## 6. Start exactly one destination Loop (separate authorization/readback)

The user's request authorizes preparing destination setup. Do not arm a second Loop while T1 is unresolved. No source-PC Loop/counter transplant. Destination timer begins with its own authentic counter; canonical run remains the same.

Check destination `/loop help` and `/loop status` in the intended Desktop session. Current source implements `/loop [interval] <prompt>` plus status/pause/resume/stop, but verify installed destination version. If a compatible destination Loop exists, inspect and reuse via supported controls, never silently replace its prompt/route/cadence. If no Loop exists, and T1-T3 pass, create one using the standalone command below in the destination SESSION (not terminal). This is a session-local scheduler, not cron. Read `/loop status` immediately afterward and record actual session, active state, cadence, owner and counter. Do not claim a firing occurred from creating it.

```text
/loop 10m Continue the SAME canonical Q0 run and the task list in docs/session-handoffs/dwa-another-pc-e2e.md. Load applicable loop/exchange/runtime skills; verify live session owner, source scope and current task frontier. Never infer authority or poll/consume mailbox from a timer. Continue independently authorized work through actual verification, not status-only waiting. Maintain short M1-M7 projections. Send browser updates only for material results or explicit user requests, exact in-app URL/auth/composer/readback, once per marker, never busy/pending duplicates or alternate transport. Preserve native Q0 state and protected effects; no W6/materialization/merge/deploy without exact applicable authority. No scheduler resets or duplicate Loops. For unchanged blockers do not repeat tests/reports/escalation. Stop only at verified acceptance or genuine boundary; LOOP_COMPLETE only for the actual verified terminal goal, never for handoff/test success. Reply Vietnamese-first with actual evidence and the next legal action.
```

Do not auto-enable Goal or Heartbeat; resolve their actual desired status separately. Do not run this slash command in the old session or create cron as a workaround.

## 7. Acceptance checklist for destination agent

- [ ] Source owner release/old Loop pause verified.
- [ ] Local branch + linked worktree exist and exact remote/head readback is clean.
- [ ] Old and new session/PC identities distinguished; one writer bound.
- [ ] Both handoff documents read and #328 correction understood.
- [ ] Native candidate/checkpoint remains preserved; new engineering HEAD not mislabeled loaded candidate.
- [ ] In-app GPT binding verified, or explicit transport blocker recorded.
- [ ] ACK marker verified in new user turn, or truthfully UNSENT/SEND_NOT_VERIFIED.
- [ ] T1-T7 and M1-M7 initialized using supported task surface.
- [ ] Exactly one destination Loop started only after prerequisites, with actual status readback; old scheduler not duplicated.
- [ ] First useful W5 action executed under source-bound scope, or exact remaining blocker identified.

## Paste into a new Hermes Desktop session on the other PC

DWA, bootstrap the same Q0 run on THIS PC end to end. Fetch repository branch `nhatnguyenquang1838-coder/gwc:fix/SCRUM-781-q0-fresh-20261010-r1`, read `docs/session-handoffs/dwa-another-pc-e2e.md` and `docs/session-handoffs/dwa-loop-recovery-641.md` fully, then execute their destination preflight, registered child worktree/local branch bootstrap, T1-T7 task creation, authenticated in-app drive_preview binding, one ACK/correction and Loop setup. Resolve this PC's paths/tools/env yourself. Do not ask me to provide technical paths or IDs available from workspace/source.

Canonical run stays `scrum781-q0-fresh-20261010-r1`; new conversation gets its real own session ID. Old source session is `20261014_021304_0dc728`. Verify old Loop pause/writer release before taking write ownership or starting a destination Loop; if unavailable, do safe read-only preflight and request that one material decision. Do not sync secrets/runtime DB or transplant counters. Do not create a duplicate scheduler. Current #328 evidence is unverified; correct it, do not use it to request premature W6. Preserve source/native/protected-state boundaries. Finish with actual verified local branch/worktree, task state, preview/ACK receipt and Loop status, or a precise blocker—not just a plan. Reply Vietnamese-first.
