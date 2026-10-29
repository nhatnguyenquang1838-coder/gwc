# DWA handoff — Loop/browser recovery after tick 641

## Scope and provenance

User explicitly requested commit and handoff to another session with a Loop prompt. This is a documentation-only continuation record, not runtime acceptance, approval, a new run, or scheduler activation. It supersedes conflicting status claims in the older laptop handoff and REPORT #328 only as an Executor correction; the Controller has not been notified successfully.

## Exact execution binding at preparation

- Old Hermes conversation/session: `20261014_021304_0dc728`.
- Canonical run: `scrum781-q0-fresh-20261010-r1`.
- Repository: `nhatnguyenquang1838-coder/gwc`.
- Branch: `fix/SCRUM-781-q0-fresh-20261010-r1`.
- Canonical worktree relative to DW-SuperApps: `worktrees/gwc/SCRUM-781-q0-fresh-20261010-r1`.
- Pre-handoff HEAD: `48f71158614ba1a10b8ab965cd971857c68339c6`; clean when inspected. Resolve the handoff commit from this file's Git history; do not assume its pre-head remains HEAD.
- Parent DW-SuperApps is a separate repository on `main`, HEAD `0f78638a9db7644c0b4e4f6fcd1b1c9ae0b760d0`; leave it and its gitlink unchanged.
- One writer only. The old session yields engineering writes for handoff; a new session must verify no old worker/turn still owns execution before taking over. New conversation identity is not a new canonical run or an automatically transferred lease.

## Durable communication references

Mailbox locator: `github://nhatnguyenquang1838-coder/gwc/issues/595`.

- COMMAND #327: https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6434766274
- REPORT #326: https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6434502907
- REPORT #328: https://github.com/nhatnguyenquang1838-coder/gwc/issues/595#issuecomment-6435418188
- REPORT #328 exact posted body SHA256: `f23295d76be410575627af43b958e8baf646294470b5d47c3257639d2e72b028`.

These are human-readable communications, not typed C/E consumption, effect authority, or approval. Do not allocate the next shared communication sequence from this document; discover it through the admitted communication path when needed.

## Mandatory correction: REPORT #328 is not verified W5 evidence

The previous Executor acknowledged these errors in chat after publishing #328:

1. B2 claimed a fresh authentic LOAD_PROOF, but code imported only `q0_qualification`, called its profile function and hashed Git blobs for other modules. It did not demonstrate importing all required modules, executing the native default route, comparing loaded module bytes to HEAD, measuring instruction surfaces or Python 3.11 identity, or enforcing no-network/write guards. Do not reuse that JSON as LOAD_PROOF.
2. B3 assigned PASS to entries by dictionary comprehension with generic evidence references. It did not independently prove the matrix and did not execute the six required focused regression files. Do not claim 11 PASS or 13/13 from it.
3. B1 checked some node ordering and allocation digest facts, but earlier probes contained guessed keys and incorrect hash assumptions. Final output did not complete all requested independent producer/digest/allocation checks. Revalidate using actual source APIs, not the old PASS_CANDIDATE label.
4. B4 classified changed `.gwc/tasks/SCRUM-781` files as stale simply from Git diff. Changed/added historical evidence is not automatically a current stale dependency. The claimed 42 stale surfaces is not a proven blocker. Read actual bindings, consumers and semantic dependencies first.
5. `certify_q0_runtime()` WAS invoked twice during probing and rejected the incomplete matrix after fixing replay-provenance digest input. Therefore “B5 NOT_RUN” is inaccurate. The observed rejection does not establish stale-state rejection; the function failed before that check.
6. Some probes used invented future timestamps and descriptive forward-progress strings. Never promote these to authentic evidence or authority.
7. No successful L3 receipt or native acceptance was demonstrated. W6 was not authorized by #327. Do not request W6 to bypass unfinished W5.

Correct status: W5 preparation is INCOMPLETE/UNVERIFIED. First useful engineering action after transport handoff is redo B0→B5 against the complete exact #327 instructions, fixing harness mistakes within scratch-only scope. No source/PR/Jira/native-cursor/scheduler effects follow from #327.

## Browser/ACK recovery

Exact user-authorized GPT Controller destination:

https://chatgpt.com/g/g-p-6a622940beac81918180ce69e50ef83c-dw-super/c/6adec292-a4a0-83ec-a9de-1d9b36f2297c

User explicitly requested ACK and then recovery/reload. ACK for REPORT #328 and its correction has NOT been sent/verified. Lack of an initial ACK is not duplicate-send evidence.

Observed recovery:
- Hermes Desktop process running; app opened/focused successfully.
- `desktop_preview(open)` and `focus_pane` returned success.
- `desktop_preview(read)` timed out; `drive_preview(elements)` returned no Desktop window answered.
- User authorized window reload. GUI Cmd+R was delivered (background then foreground after unverifiable input). Capture remained available but did not establish main-window reload completion or restored preview bridge.
- No app/backend restart, core/config change, alternate GPT browser transport, credential entry, or scheduler mutation was performed.

New session: verify exact in-app URL, authentication, page liveness and empty composer using current read/elements before one uniquely marked ACK/correction. If bridge remains unavailable, retain `IN_APP_BROWSER_UNAVAILABLE` / `SEND_NOT_VERIFIED`; do not switch to external Chrome, browser_exec, raw HTTP, clipboard, or another URL. Do not send while GPT is busy or if the correction marker is already present. Verify new user turn, not just composer clear.

Suggested ACK substance (only after binding verification): same run/branch continues; REPORT #328 is unverified and its LOAD_PROOF/matrix/stale/B5 claims are withdrawn pending proper scratch-only B0→B5 re-execution under #327; no native qualification/acceptance or W6 advancement claimed.

## Loop continuity: unresolved runtime discrepancy

- Historical CLI checks at ticks 640/641 said active, `ticks_fired=640/641`, `awaiting_response=true`.
- Later read-only `LoopManager` calls for the same environment session returned `state=None`; environment platform was `local` despite Desktop use.
- Previous assistant subsequently reported UI showing “active · 641 runs · due — waiting for idle”; this is a reported UI observation, not a verified database reconciliation. Reinspect live UI and actual Desktop backend/profile store before treating either as canonical.
- Goal/Heartbeat pause claims are historical; not freshly verified at handoff.
- No Loop reset/resume/rearm/settle/stop or counter transfer was performed. The user asked for a prompt, not for a second concurrent scheduler.

A timer does not authorize mailbox polling/consumption or protected effects. Do not create a second Loop in the new session while the old one may still fire. Resolve owner/store/session binding and use supported controls with explicit user authority for any migration. Do not mutate SQLite directly or kill the old session to repair counters.

## Other workstreams and boundaries

Q0 remains OPEN/unaccepted. Historical native candidate `5e40763b63b27873ac2cff30ac10f0eeef5a5469`, cursor `UR.G6/seq7` are pointers requiring exact runtime readback, not current-head qualification. W4 historical replay was accepted for W5 entry by #327; original DWO remains NOT_REPRODUCED. ACK65 is Controller-observed Human-decision attestation, not raw Human authentication.

Workstream A remains read/inspect/isolated-compute pending applicable decisions/authority. Generic D3/PR613/SCRUM-846 and SCRUM-848 preparation remain separate; do not reopen them as Q0 prerequisites. No merge/Ready/deploy/main/production/config/secret/migration/destructive effect, reset/rebase/force-push, or parent gitlink bump.

## Copy-ready new-session prompt

Continue DWA from session `20261014_021304_0dc728` using the committed file `docs/session-handoffs/dwa-loop-recovery-641.md` in GWC worktree `worktrees/gwc/SCRUM-781-q0-fresh-20261010-r1`. Read it fully first. Preserve run `scrum781-q0-fresh-20261010-r1`, same branch/worktree, one writer, additive history. This is a new conversation, not a new canonical execution.

Load `hermes-session-handoff`, `hermes-loop-operations`, `dwa-gpt-exchange`, and applicable runtime-certification/source contracts. Verify local/remote state and writer ownership. Do not assume TaskController activation from a mailbox locator; if already bound and applicable, load its canonical chain and coordination skill.

First reconcile Desktop Loop/store/owner: old Loop may still be active at 641, while CLI returned None. Do not create duplicate Loop or transfer/reset counters. Do not interpret this prompt as permission to rearm a scheduler. Use an interactive recovery turn until the discrepancy is resolved.

Recover the in-app GPT preview at the exact URL in the handoff. User has requested ACK/correction. Verify URL/auth/composer/liveness, send once with a fresh unique marker only if absent and idle, and exact-read the new user turn. Do not use alternate GPT transport or credentials. REPORT #328 is unverified: explicitly correct its unsupported LOAD_PROOF, assigned PASS matrix, changed-file stale inference, and contradictory B5 NOT_RUN claim. Browser ACK is not execution authority.

Then continue independently authorized scratch-only W5 work under complete exact COMMAND #327: B0→B5, genuine measured fresh Python 3.11 load/route, canonical DAG/allocation/digest validation, evidence-per-entry matrix and required focused regressions, semantic stale-dependency assessment and conditional pure certification. Preserve native artifacts and stop before materialization/W6. Do not repeat unchanged tests merely for status, invent PASS/authority, or stop at routine harness fixes. Report only actual evidence and exact target readback.

For every legitimate future Loop firing: verify live owner/counter/scope; update concise M1–M7 projection; perform smallest useful authorized work to verification or a real boundary; no timer mailbox polling, duplicate ACK/report, scheduler mutation or unverified LOOP_COMPLETE. Respond Vietnamese-first. Terminal acceptance requires actual verified acceptance, not test success or a handoff commit.
